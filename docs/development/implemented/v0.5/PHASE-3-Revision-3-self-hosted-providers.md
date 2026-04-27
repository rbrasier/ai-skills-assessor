# Phase 3 Revision 3 — Self-Hosted STT/TTS Providers

**Version:** v0.5.0  
**Date implemented:** 2026-04-27  
**Branch:** `claude/add-self-hosted-providers-ZFsay`

---

## Overview

This revision adds a **swappable provider abstraction layer** for the two AI services
that are active during every assessment call:

| Service | Cloud provider (default) | Self-hosted alternative |
|---------|--------------------------|-------------------------|
| STT     | Deepgram                 | faster-whisper (CPU) on Railway |
| TTS     | ElevenLabs               | Kokoro-FastAPI (CPU) on Railway |

Provider selection is controlled by environment variables and includes graceful
fallback to the cloud provider when the self-hosted URL is unset or the service
is unreachable.

---

## Motivation

- **Cost control during testing.** Both Deepgram and ElevenLabs charge per
  second/character. Self-hosted alternatives let QA teams run unlimited
  assessments without API costs.
- **Data sovereignty.** Some clients require that audio never leaves their
  infrastructure boundary.
- **Offline / airgapped demos.** With Kokoro + Whisper deployed on Railway, the
  full pipeline can run without any external AI API keys.
- **Railway CPU-only constraint.** The chosen models (`tiny.en` for Whisper,
  Kokoro base for TTS) are specifically tuned to run acceptably on Railway Hobby
  (CPU-only, 4 GB / 2 GB RAM).

---

## Architecture

### Hexagonal architecture compliance

The abstraction layer sits entirely in the **adapters** layer — consistent with
ADR-001. The `packages/core` domain layer is untouched; it already communicates
with STT/TTS via Pipecat frame types (`AudioRawFrame`, `TranscriptionFrame`,
`TTSSpeakFrame`) which are framework-agnostic from the domain's perspective.

```
apps/voice-engine/src/
├── adapters/
│   ├── stt/
│   │   ├── __init__.py           ← exports create_stt_service
│   │   ├── factory.py            ← selects Deepgram or Whisper; graceful fallback
│   │   └── whisper_stt_service.py← Pipecat FrameProcessor → WebSocket client
│   └── tts/
│       ├── __init__.py           ← exports create_tts_service
│       ├── factory.py            ← selects ElevenLabs or Kokoro; graceful fallback
│       └── kokoro_tts_service.py ← Pipecat FrameProcessor → HTTP streaming client
├── flows/
│   └── bot_runner.py             ← updated: calls factory functions instead of
│                                    hardcoded DeepgramSTTService / ElevenLabsTTSService
└── api/
    └── routes.py                 ← /tts-test endpoint now provider-aware
```

### Pipeline integration

The factory functions return Pipecat-compatible `FrameProcessor` objects that
slot directly into the existing pipeline at the same position as the original
services:

```python
# Before (hardcoded):
stt = DeepgramSTTService(api_key=..., model=...)
tts = ElevenLabsTTSService(api_key=..., voice_id=..., output_format=...)

# After (factory-driven):
from src.adapters.stt import create_stt_service
from src.adapters.tts import create_tts_service
stt = create_stt_service(self._settings)
tts = create_tts_service(self._settings)
```

No other code paths change. The pipeline `[transport.input(), stt, conversation, tts, transport.output()]` is identical.

---

## New environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `STT_PROVIDER` | `deepgram` | `deepgram` or `whisper` |
| `WHISPER_STT_URL` | *(empty)* | WebSocket URL of the Whisper STT server, e.g. `wss://whisper-stt.up.railway.app/ws/transcribe` |
| `TTS_PROVIDER` | `elevenlabs` | `elevenlabs` or `kokoro` |
| `KOKORO_TTS_URL` | *(empty)* | Base HTTP URL of the Kokoro TTS server, e.g. `https://kokoro-tts.up.railway.app` |
| `KOKORO_VOICE` | `af_bella` | Kokoro voice identifier |
| `KOKORO_SAMPLE_RATE` | `24000` | PCM sample rate for Kokoro output (Hz) |

All existing `DEEPGRAM_*` and `ELEVENLABS_*` variables are unchanged and remain active when those providers are selected.

---

## Self-hosted services

### Whisper STT (`apps/whisper-stt/`)

A new standalone FastAPI service built from scratch:

- **Framework:** FastAPI + Uvicorn
- **Model:** `faster-whisper` `tiny.en` (baked into Docker image at build time)
- **VAD:** Silero VAD (PyTorch, CPU) — detects speech boundaries to segment audio
- **Protocol:** Binary WebSocket — client sends raw PCM (16 kHz, 16-bit mono); server returns JSON `{"text": "...", "is_final": true|false, "duration_ms": N}`
- **Health:** `GET /health` → `{"status": "ok", "model": "tiny.en"}`
- **Memory:** 4 GB recommended (Railway: set service memory limit)
- **Railway config:** `apps/whisper-stt/railway.json`

The Pipecat client (`whisper_stt_service.py`) connects on `StartFrame`, sends `AudioRawFrame.audio` bytes over the WebSocket, suppresses audio from propagating further downstream, and pushes `TranscriptionFrame` / `InterimTranscriptionFrame` events when the server responds.

### Kokoro TTS (`ghcr.io/remsky/kokoro-fastapi-cpu:latest`)

A pre-built public Docker image — no build step required:

- **Image:** `ghcr.io/remsky/kokoro-fastapi-cpu:latest`
- **API:** OpenAI-compatible `/v1/audio/speech` endpoint
- **Request:** `{"model": "kokoro", "input": "<text>", "voice": "af_bella", "response_format": "pcm", "speed": 1.0}`
- **Response:** streaming raw PCM bytes (16-bit mono, 24 kHz)
- **Health:** `GET /health`
- **Memory:** 2 GB recommended

The Pipecat client (`kokoro_tts_service.py`) receives `TTSSpeakFrame` objects, calls the streaming HTTP endpoint via `httpx`, and emits `AudioRawFrame` chunks as they arrive — identical to what `ElevenLabsTTSService` produces.

---

## Graceful fallback

Both factories perform a lightweight health probe before returning the
self-hosted processor:

1. **URL missing** → log `WARNING` + return cloud provider.
2. **Health probe fails** (HTTP error or timeout ≤ 3 s) → log `ERROR` + return cloud provider.
3. **Health probe passes** → log `INFO` with the active provider URL + return self-hosted processor.

This means:
- Setting `STT_PROVIDER=whisper` without `WHISPER_STT_URL` silently uses Deepgram.
- A Railway outage of the Whisper service causes an automatic fall-through to Deepgram for the next pipeline start.
- Startup logs always clearly indicate which provider is active.

---

## `/tts-test` endpoint changes

`GET /tts-test` is now **provider-aware**:

- When `TTS_PROVIDER=elevenlabs` (default): calls ElevenLabs directly (unchanged behaviour).
- When `TTS_PROVIDER=kokoro`: calls Kokoro's `/v1/audio/speech` endpoint and streams the PCM response.
- Both paths return a `audio/wav` response with a valid RIFF header.
- Returns `503` with `"ELEVENLABS_API_KEY not configured"` or `"KOKORO_TTS_URL not configured"` when the required setting is missing.

---

## Docker Compose profiles

`docker-compose.yml` now supports three optional profiles:

| Profile | Services activated | Use case |
|---------|-------------------|----------|
| `stt` | `whisper-stt` | Self-hosted STT only |
| `tts` | `kokoro-tts` | Self-hosted TTS only |
| `selfhosted` | `whisper-stt` + `kokoro-tts` | Both self-hosted |

Usage:
```bash
# Both self-hosted
STT_PROVIDER=whisper TTS_PROVIDER=kokoro \
  docker compose --profile selfhosted up --build
```

Port assignments:
- `whisper-stt`: `8001` (local) → `$PORT` (Railway)
- `kokoro-tts`: `8880` (local) → `$PORT` (Railway)

---

## Tests added

| Test file | What it tests |
|-----------|---------------|
| `tests/test_stt_factory.py` | Settings validation, deepgram/whisper selection, fallback when URL missing, fallback when unreachable |
| `tests/test_tts_factory.py` | Settings validation, elevenlabs/kokoro selection, fallback cases, `/tts-test` endpoint with Kokoro |
| `tests/test_providers_smoke.py` | Live-URL smoke tests: `/health` version check, `/tts-test` WAV validation, Whisper/Kokoro health probes |

All new tests run in the lean CI install (`pip install -e ".[dev]"`) without the `[voice]` extras. Pipecat-specific code paths are exercised only via patching/mocking.

---

## validate.sh additions

`validate.sh` now runs three additional checks (11–13):

- **Check 11:** `test_stt_factory.py` + `test_tts_factory.py` unit tests.
- **Check 12:** All required provider adapter files are present.
- **Check 13:** Provider smoke tests against `SMOKE_TEST_URL` (requires `--smoke` flag).

---

## Deployment notes

### Railway — Whisper STT service

1. Create a new Railway service from the GitHub repo.
2. Set **Root Directory** to `apps/whisper-stt`.
3. Set **Builder** to Dockerfile; Railway auto-detects `apps/whisper-stt/railway.json`.
4. Set **Memory limit** to **4096 MB** in Settings → Resources.
5. After deploy, copy the public URL and set `WHISPER_STT_URL=wss://<url>/ws/transcribe` on the `voice-engine` service.

Health check timeout is set to **300 s** in `railway.json` because the Silero VAD
model needs to download from `torch.hub` on the first cold start (~2 min).
Subsequent starts use Docker layer cache and start in < 30 s.

### Railway — Kokoro TTS service

Kokoro already has a Railway one-click template. Either:

- Use the template from the Kokoro-FastAPI GitHub page, **or**
- Create a new service: Docker Image → `ghcr.io/remsky/kokoro-fastapi-cpu:latest`, Memory: **2048 MB**.

After deploy, copy the public URL and set `KOKORO_TTS_URL=https://<url>` on the `voice-engine` service.

### setup-on-railway.sh

`docs/guides/setup-on-railway.sh` was updated to:
- Prompt for `STT_PROVIDER` and `TTS_PROVIDER` interactively.
- Conditionally prompt for cloud API keys (skipped when self-hosted is selected).
- Conditionally prompt for self-hosted service URLs.
- Print manual steps for creating the Whisper/Kokoro Railway services.

---

## Acceptance criteria

- [x] `STT_PROVIDER=deepgram` (default) → Deepgram STT used (no behaviour change)
- [x] `TTS_PROVIDER=elevenlabs` (default) → ElevenLabs TTS used (no behaviour change)
- [x] `STT_PROVIDER=whisper` + valid URL → Whisper WebSocket client used in pipeline
- [x] `TTS_PROVIDER=kokoro` + valid URL → Kokoro HTTP client used in pipeline
- [x] Missing URL → warning logged + cloud fallback
- [x] Unreachable service → error logged + cloud fallback
- [x] `/tts-test` endpoint returns WAV for both providers
- [x] `docker compose --profile selfhosted up` starts Whisper + Kokoro alongside voice-engine
- [x] `validate.sh` passes all 13 checks with new provider tests
- [x] Unit tests pass without Pipecat voice extras installed
