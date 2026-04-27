"""faster-whisper WebSocket STT server.

Accepts raw PCM audio chunks over a WebSocket connection, uses Silero VAD to
detect speech boundaries, and transcribes speech with faster-whisper.

Protocol
--------
Client → Server: binary frames, each containing raw PCM bytes
                 (16 kHz, mono, 16-bit little-endian signed integers)

Server → Client: JSON text frames

    Interim (VAD speech detected, not yet at a boundary):
        {"text": "<partial>", "is_final": false, "duration_ms": <int>}

    Final (silence detected after speech — segment complete):
        {"text": "<final>", "is_final": true, "duration_ms": <int>}

    Error:
        {"error": "<message>"}

Endpoints
---------
GET  /health          — liveness probe (used by Railway + graceful-fallback logic)
WS   /ws/transcribe   — audio ingestion + transcript stream
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections import deque
from typing import Any

import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────────────

MODEL_SIZE: str = os.getenv("WHISPER_MODEL", "tiny.en")
SAMPLE_RATE: int = 16_000
# Silero VAD threshold (0–1). Lower = more sensitive to quiet speech.
VAD_THRESHOLD: float = float(os.getenv("VAD_THRESHOLD", "0.5"))
# Minimum silence duration (ms) after speech before emitting a final transcript.
SILENCE_DURATION_MS: int = int(os.getenv("SILENCE_DURATION_MS", "700"))
# Maximum audio buffer size (seconds) before forcing a transcription flush.
MAX_BUFFER_SECONDS: float = float(os.getenv("MAX_BUFFER_SECONDS", "30.0"))

# ── Model loading ─────────────────────────────────────────────────────────────

_whisper_model: Any = None
_vad_model: Any = None
_vad_utils: Any = None
_model_lock = asyncio.Lock()


def _load_models() -> None:
    """Load faster-whisper and Silero VAD models (blocking — call once at startup)."""
    global _whisper_model, _vad_model, _vad_utils  # noqa: PLW0603

    logger.info("Loading faster-whisper model: %s", MODEL_SIZE)
    from faster_whisper import WhisperModel  # type: ignore[import]

    _whisper_model = WhisperModel(
        MODEL_SIZE,
        device="cpu",
        compute_type="int8",
        num_workers=1,
    )
    logger.info("faster-whisper model loaded")

    logger.info("Loading Silero VAD model")
    import torch  # type: ignore[import]

    _vad_model, utils = torch.hub.load(
        repo_or_dir="snakers4/silero-vad",
        model="silero_vad",
        force_reload=False,
        onnx=False,
    )
    _vad_utils = utils
    logger.info("Silero VAD model loaded")


# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(title="whisper-stt", version="1.0.0")


@app.on_event("startup")
async def _startup() -> None:
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _load_models)
    logger.info("whisper-stt ready")


@app.get("/health")
async def health() -> JSONResponse:
    ready = _whisper_model is not None and _vad_model is not None
    code = 200 if ready else 503
    return JSONResponse(
        {"status": "ok" if ready else "loading", "model": MODEL_SIZE},
        status_code=code,
    )


# ── WebSocket transcription ────────────────────────────────────────────────────


@app.websocket("/ws/transcribe")
async def ws_transcribe(ws: WebSocket) -> None:
    await ws.accept()
    logger.info("WebSocket client connected")

    # Per-connection state
    audio_buffer: deque[bytes] = deque()
    buffer_samples: int = 0
    in_speech: bool = False
    silence_start: float | None = None

    import torch  # type: ignore[import]

    loop = asyncio.get_event_loop()

    async def _flush_and_send(is_final: bool) -> None:
        nonlocal buffer_samples, in_speech, silence_start
        if buffer_samples == 0:
            return

        pcm_bytes = b"".join(audio_buffer)
        audio_buffer.clear()
        duration_ms = int(buffer_samples / SAMPLE_RATE * 1000)
        buffer_samples = 0
        in_speech = False
        silence_start = None

        # Transcribe on the thread pool so the event loop stays unblocked.
        text = await loop.run_in_executor(None, _transcribe, pcm_bytes)
        if text.strip():
            await ws.send_text(
                json.dumps({"text": text, "is_final": is_final, "duration_ms": duration_ms})
            )

    try:
        while True:
            try:
                raw = await asyncio.wait_for(ws.receive_bytes(), timeout=5.0)
            except asyncio.TimeoutError:
                # No audio received for 5 s — if we have buffered speech, flush it.
                if in_speech and buffer_samples > 0:
                    await _flush_and_send(is_final=True)
                continue

            # Convert bytes → float32 waveform for VAD
            pcm_int16 = np.frombuffer(raw, dtype=np.int16)
            if pcm_int16.size == 0:
                continue
            waveform = torch.from_numpy(pcm_int16.astype(np.float32) / 32768.0)

            # Silero VAD expects 512-sample chunks at 16 kHz
            speech_prob: float = _vad_model(waveform, SAMPLE_RATE).item()
            is_speech_chunk = speech_prob >= VAD_THRESHOLD

            now = time.monotonic()

            if is_speech_chunk:
                audio_buffer.append(raw)
                buffer_samples += pcm_int16.size
                in_speech = True
                silence_start = None

                # Emit interim so the client sees activity
                if buffer_samples >= SAMPLE_RATE // 2:  # every ~500 ms
                    pcm_so_far = b"".join(audio_buffer)
                    partial = await loop.run_in_executor(None, _transcribe, pcm_so_far)
                    if partial.strip():
                        await ws.send_text(
                            json.dumps({
                                "text": partial,
                                "is_final": False,
                                "duration_ms": int(buffer_samples / SAMPLE_RATE * 1000),
                            })
                        )

                # Force flush if buffer is too long
                if buffer_samples >= int(SAMPLE_RATE * MAX_BUFFER_SECONDS):
                    await _flush_and_send(is_final=False)

            else:
                if in_speech:
                    if silence_start is None:
                        silence_start = now
                    silence_elapsed_ms = (now - silence_start) * 1000
                    if silence_elapsed_ms >= SILENCE_DURATION_MS:
                        await _flush_and_send(is_final=True)
                # Not in speech: discard this chunk (background noise)

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as exc:
        logger.exception("WebSocket handler error: %s", exc)
        try:
            await ws.send_text(json.dumps({"error": str(exc)}))
        except Exception:
            pass
    finally:
        try:
            await ws.close()
        except Exception:
            pass


def _transcribe(pcm_bytes: bytes) -> str:
    """Synchronous faster-whisper transcription — runs on a thread-pool worker."""
    import numpy as np

    if _whisper_model is None:
        return ""
    pcm_int16 = np.frombuffer(pcm_bytes, dtype=np.int16)
    waveform = pcm_int16.astype(np.float32) / 32768.0
    segments, _ = _whisper_model.transcribe(
        waveform,
        language="en",
        beam_size=1,
        best_of=1,
        temperature=0.0,
        vad_filter=False,  # VAD already applied upstream
        word_timestamps=False,
    )
    return " ".join(s.text.strip() for s in segments if s.text.strip())
