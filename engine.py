"""
engine.py - Audio capture + streaming-ish transcription using faster-whisper.

Strategy:
- Continuously record audio into a rolling buffer while "listening" is on.
- Every CHUNK_SECONDS, transcribe the buffered audio so far (with a bit of
  overlap from the previous chunk for context) and emit new text via a
  callback. This gives a "live-ish" feel without true frame-level streaming.
"""

import threading
import time
import queue
import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel

from log_setup import get_logger

log = get_logger("engine")

SAMPLE_RATE = 16000

# Whisper is well-known to hallucinate these specific phrases on quiet,
# ambiguous, or silence-adjacent audio - almost certainly an artifact of
# its training data (lots of YouTube/podcast outros). We filter short
# transcriptions that exactly match one of these, since a real utterance
# of just "thank you" alone via dictation is rare, while the hallucination
# is common.
KNOWN_HALLUCINATION_PHRASES = {
    "thank you",
    "thank you.",
    "thanks for watching",
    "thanks for watching.",
    "bye",
    "bye.",
    "bye bye",
    "you",
    "the",
    "okay",
    "okay.",
    "i'm sorry",
    "i'm sorry.",
    "subscribe",
    "please subscribe",
}


class TranscriptionEngine:
    def __init__(self, on_text, on_status=None, cfg=None):
        """
        on_text(str): called with each new finalized text chunk
        on_status(str): called with status updates ("listening", "stopped", "loading", "error: ...")
        cfg(dict): config values - model_size, device, compute_type, chunk_seconds, overlap_seconds
        """
        cfg = cfg or {}
        self.on_text = on_text
        self.on_status = on_status or (lambda s: None)
        self.model_size = cfg.get("model_size", "small")
        self.device = cfg.get("device", "cuda")
        self.compute_type = cfg.get("compute_type", "float16")
        self.chunk_seconds = float(cfg.get("chunk_seconds", 2.5))
        self.overlap_seconds = float(cfg.get("overlap_seconds", 0.5))
        self.vad_filter = bool(cfg.get("vad_filter", False))
        self.silence_rms_threshold = float(cfg.get("silence_rms_threshold", 0.01))
        self.hallucination_logprob_threshold = float(cfg.get("hallucination_logprob_threshold", -0.5))
        log.info("Engine configured: model_size=%s chunk_seconds=%.2f vad_filter=%s silence_rms_threshold=%s",
                 self.model_size, self.chunk_seconds, self.vad_filter, self.silence_rms_threshold)

        self._model = None
        self._listening = False
        self._audio_q = queue.Queue()
        self._buffer = np.zeros((0,), dtype=np.float32)
        self._worker_thread = None
        self._stream = None
        self._lock = threading.Lock()
        self._start_lock = threading.Lock()

    def _emit_status(self, status):
        try:
            self.on_status(status)
        except Exception:
            pass

    def load_model(self):
        if self._model is not None:
            log.debug("Model already loaded, skipping reload.")
            return
        self._emit_status("loading")
        log.info("Loading Whisper model '%s' on device=%s compute_type=%s", self.model_size, self.device, self.compute_type)
        try:
            self._model = WhisperModel(self.model_size, device=self.device, compute_type=self.compute_type)
            log.info("Model loaded successfully on %s.", self.device)
        except Exception as e:
            log.warning("GPU load failed (%s), falling back to CPU.", e)
            try:
                self._model = WhisperModel(self.model_size, device="cpu", compute_type="int8")
                self._emit_status("loaded (cpu fallback)")
                log.info("Model loaded successfully on CPU (fallback).")
            except Exception as e2:
                log.error("Model failed to load on CPU as well: %s", e2, exc_info=True)
                self._emit_status(f"error: failed to load model ({e2})")
                raise
        else:
            self._emit_status("loaded")

    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            log.warning("Audio stream status flag: %s", status)
        self._audio_q.put(indata.copy().reshape(-1))

    def start(self):
        with self._start_lock:
            if self._listening:
                log.debug("start() called but already listening.")
                return
            log.info("Starting listening session.")
            self.load_model()
            self._listening = True
            self._buffer = np.zeros((0,), dtype=np.float32)

            try:
                self._stream = sd.InputStream(
                    samplerate=SAMPLE_RATE,
                    channels=1,
                    dtype="float32",
                    callback=self._audio_callback,
                )
                self._stream.start()
                log.info("Audio input stream opened (sample_rate=%d).", SAMPLE_RATE)
            except Exception as e:
                log.error("Failed to open audio input stream: %s", e, exc_info=True)
                self._listening = False
                self._emit_status(f"error: microphone unavailable ({e})")
                return

            self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
            self._worker_thread.start()
            self._emit_status("listening")

    def stop(self):
        if not self._listening:
            log.debug("stop() called but not currently listening.")
            return
        log.info("Stopping listening session.")
        self._listening = False
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        self._emit_status("stopped")

    def is_listening(self):
        return self._listening

    def _worker_loop(self):
        last_transcribe_time = time.time()

        while self._listening:
            try:
                chunk = self._audio_q.get(timeout=0.2)
                self._buffer = np.concatenate([self._buffer, chunk])
            except queue.Empty:
                pass

            now = time.time()
            if now - last_transcribe_time >= self.chunk_seconds and len(self._buffer) > 0:
                self._transcribe_buffer()
                last_transcribe_time = now

        # Final flush on stop
        if len(self._buffer) > 0:
            self._transcribe_buffer(final=True)

    def _looks_like_hallucination(self, text: str, avg_logprob: float) -> bool:
        """Heuristic check for likely Whisper hallucinations: either an
        exact match against known phantom phrases, or low-confidence short
        output (a handful of words with a poor average log-probability is
        a strong hallucination signal, especially right after the silence
        gate already let this chunk through)."""
        normalized = text.strip().lower()

        if normalized in KNOWN_HALLUCINATION_PHRASES:
            return True

        word_count = len(normalized.split())
        if word_count <= 3 and avg_logprob < self.hallucination_logprob_threshold:
            return True

        return False

    def _transcribe_buffer(self, final=False):
        with self._lock:
            audio = self._buffer.copy()

        if len(audio) < SAMPLE_RATE * 0.3:  # skip near-empty chunks
            log.debug("Skipping transcription, buffer too short (%d samples).", len(audio))
            return

        # Lightweight silence gate: skip chunks that are mostly quiet/background
        # noise rather than actual speech. This isn't as accurate as real VAD
        # (Silero, via onnxruntime), but it catches the common case of
        # Whisper hallucinating random words on near-silent audio, without
        # needing onnxruntime to be working.
        rms = float(np.sqrt(np.mean(np.square(audio))))
        if rms < self.silence_rms_threshold:
            log.debug("Skipping transcription, audio below silence threshold (rms=%.5f).", rms)
            return

        start_t = time.time()
        try:
            segments, _info = self._model.transcribe(
                audio,
                language="en",
                vad_filter=self.vad_filter,
                vad_parameters=dict(min_silence_duration_ms=300) if self.vad_filter else None,
                no_speech_threshold=0.6,
                condition_on_previous_text=False,
            )
            segments = list(segments)
            text = " ".join(seg.text.strip() for seg in segments).strip()
            avg_logprob = (
                sum(seg.avg_logprob for seg in segments) / len(segments)
                if segments else 0.0
            )
        except Exception as e:
            log.error("Transcription failed: %s", e, exc_info=True)
            self._emit_status(f"error: {e}")
            return

        elapsed = time.time() - start_t

        if text and self._looks_like_hallucination(text, avg_logprob):
            log.debug(
                "Dropping likely hallucination (%.2fs audio, avg_logprob=%.3f) -> %r",
                len(audio) / SAMPLE_RATE, avg_logprob, text,
            )
            text = ""

        if text:
            log.info("Transcribed %.2fs audio in %.2fs -> %r", len(audio) / SAMPLE_RATE, elapsed, text)
            self.on_text(text)
        else:
            log.debug("Transcription produced no text (%.2fs audio, %.2fs elapsed) - likely silence.", len(audio) / SAMPLE_RATE, elapsed)

        # Keep a small overlap tail of raw audio for context, discard the rest
        overlap_samples = int(self.overlap_seconds * SAMPLE_RATE)
        with self._lock:
            if len(self._buffer) > overlap_samples:
                self._buffer = self._buffer[-overlap_samples:]
