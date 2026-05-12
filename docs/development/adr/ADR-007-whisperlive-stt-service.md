# ADR-007: Replace Custom Whisper STT Build with WhisperLive

## Status
Accepted

## Date
2026-05-11

## Context

Phase 3 introduced a self-hosted STT option built around a custom Docker image
(`apps/whisper-stt/`) that bundled faster-whisper, Silero VAD, and a bespoke
FastAPI/WebSocket server. This image had to be built locally or on Railway before
it could be used, and it accumulated several reliability issues during debugging:

- WebSocket reconnection required manual cooldown logic in the Pipecat adapter.
- VAD tuning (threshold, silence duration) was managed entirely in custom Python,
  with no upstream support or community testing.
- Silero VAD integration required torch + torchaudio (~600 MB) in the image,
  inflating build times and cold-start latency.
- The Docker build itself was fragile — model pre-download during `docker build`
  is sensitive to network conditions and layer caching.
- Every faster-whisper or torch upgrade required a manual image rebuild and
  re-push.

The decision was made to replace the custom build with a maintained, pre-built
Docker image that provides equivalent streaming STT on CPU, removing the need
to maintain application-level VAD and WebSocket server code.

## Options Considered

### Option 1: WhisperLive (collabora/WhisperLive)

| Property | Detail |
|---|---|
| Stars | ~4,000 |
| Last commit | May 8, 2026 |
| Stable release | v0.8.0 (March 2026) |
| CPU Docker image | `ghcr.io/collabora/whisperlive-cpu:latest` |
| Backend | faster-whisper + CTranslate2 (same as custom build) |
| Streaming protocol | Custom WebSocket (port 9090) with JSON handshake |
| OpenAI API compat | Partial (batch REST only, optional flag) |
| Pipecat integration | Requires custom adapter (existing pattern in codebase) |
| Known issues | Python 3.13 incompat in container (does not affect adapter) |
| Maintenance | Collabora (commercial entity); active security + reliability work |

### Option 2: speaches (speaches-ai/speaches)

| Property | Detail |
|---|---|
| Stars | ~3,300 |
| Last commit | April 18, 2026 |
| Stable release | v0.9.0-rc.3 only (RC since December 2024 — no stable release) |
| CPU Docker image | `ghcr.io/speaches-ai/speaches:latest-cpu` |
| Backend | faster-whisper + CTranslate2 |
| Streaming protocol | OpenAI Realtime API WebSocket (`/v1/realtime`) |
| OpenAI API compat | Full |
| Pipecat integration | Native via `OpenAIRealtimeSTTService` with `base_url` override |
| Known issues | Memory leak on model unload (#629, #638) — unresolved as of May 2026 |
| Maintenance | Community continuation of archived `fedirz/faster-whisper-server` |

### Option 3: Keep the custom build

Continue maintaining `apps/whisper-stt/` with fixes for the VAD and reconnection
issues already merged. No integration changes required.

## Decision

**WhisperLive** is selected.

The deciding factors are:

1. **Production reliability**: WhisperLive v0.8.0 is a stable release maintained
   by Collabora. speaches has been on a release candidate since December 2024 and
   has two unresolved memory leak issues (#629, #638) that directly affect
   long-running voice pipeline containers. A memory leak in a per-call STT service
   is a critical production concern.

2. **No custom image build**: `ghcr.io/collabora/whisperlive-cpu:latest` is a
   pre-built, versioned image. It is pulled on first use, eliminating the
   network-sensitive model download step from `docker build`.

3. **Adapter pattern is established**: The codebase already has a custom Pipecat
   adapter layer (`apps/voice-engine/src/adapters/stt/`). Adapting to the
   WhisperLive WebSocket protocol is a straightforward port-level change within
   that existing pattern — not meaningfully more work than the speaches
   `base_url` approach.

4. **VAD offloaded upstream**: WhisperLive handles VAD internally. The custom
   Silero VAD integration, torch dependency, and silence-duration tuning are
   removed from application code entirely.

5. **Recent activity quality**: WhisperLive's May 2026 commits address thread
   safety, bounded transcript memory, and input validation — the same classes of
   issues that caused debugging rounds in the custom build.

speaches is not selected primarily due to the unresolved memory leaks and the
extended release-candidate period. If those issues are resolved in a future stable
release, speaches remains a viable future option because its OpenAI Realtime API
compatibility would allow removing the custom adapter entirely.

The custom build is retired — its `apps/whisper-stt/` directory is deleted.

## Architecture Change

### Before

```
voice-engine ──ws──► apps/whisper-stt (custom build)
                       faster-whisper + Silero VAD
                       FastAPI + custom WebSocket server
                       Binary PCM → {"text": "...", "is_final": true}
```

### After

```
voice-engine ──ws──► ghcr.io/collabora/whisperlive-cpu (pre-built)
                       faster-whisper + built-in VAD
                       WhisperLive WebSocket server (port 9090)
                       JSON handshake + Binary PCM → {"segments": [...]}
```

### WhisperLive WebSocket Protocol

**Connection sequence:**

1. Client connects to `ws://host:9090`
2. Client sends JSON handshake:
   ```json
   {"uid": "<uuid4>", "language": "en", "task": "transcribe",
    "model": "tiny.en", "use_vad": true, "send_last_n_segments": 10}
   ```
3. Server responds with `{"uid": "...", "message": "SERVER_READY"}`
   (or `{"uid": "...", "status": "WAIT"}` if the server is at capacity)
4. Client streams raw binary PCM (16-bit, mono, 16 kHz)
5. Server streams JSON transcript messages:
   ```json
   {"uid": "...", "segments": [
     {"text": "hello world", "start": 0.0, "end": 1.5, "completed": true},
     {"text": "how are",     "start": 1.5, "end": 2.1, "completed": false}
   ], "language": "en"}
   ```
   - `completed: true` — segment is finalised and will not change
   - `completed: false` — segment is still being refined (interim)
6. On disconnect, client sends `b"END_OF_AUDIO"` sentinel

**Adapter mapping to Pipecat frames:**

| WhisperLive event | Pipecat frame |
|---|---|
| New segment with `completed: true` | `TranscriptionFrame` |
| Latest segment with `completed: false` | `InterimTranscriptionFrame` |

### Configuration

| Setting | Value |
|---|---|
| `STT_PROVIDER` | `whisper` (unchanged) |
| `WHISPER_STT_URL` | `ws://whisper-stt:9090` (port changed from 8001) |
| Docker image | `ghcr.io/collabora/whisperlive-cpu:latest` |
| Container port | `9090` |
| Health check | TCP connect to port 9090 (WhisperLive has no HTTP health endpoint) |

## Consequences

**Positive:**
- No custom Docker image to build or maintain.
- VAD, silence detection, and transcript buffering are handled by WhisperLive.
- Commercially-backed project with active maintenance.
- Stable release available; container pinnable to a specific tag.
- `OMP_NUM_THREADS` env var allows CPU thread tuning without code changes.

**Negative:**
- WhisperLive's WebSocket protocol requires a custom Pipecat adapter (maintained
  in `apps/voice-engine/src/adapters/stt/whisper_stt_service.py`). If
  WhisperLive changes its wire protocol, the adapter must be updated.
- No HTTP health endpoint — the restart script and docker-compose use a TCP
  port check instead of an HTTP liveness probe.
- Model size is not configurable via a simple env var on the pre-built CPU image;
  the default (tiny) is appropriate for latency-sensitive telephony use.

## References

- [collabora/WhisperLive on GitHub](https://github.com/collabora/WhisperLive)
- [WhisperLive v0.8.0 release](https://github.com/collabora/WhisperLive/releases/tag/v0.8.0)
- [ADR-004: Voice Engine Technology](ADR-004-voice-engine-technology.md)
- [ADR-001: Hexagonal Architecture](ADR-001-hexagonal-architecture.md)
