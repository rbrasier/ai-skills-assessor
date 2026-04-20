# ADR-004: Voice Engine Technology Decisions (Pipecat, Daily, FastAPI)

## Status
Accepted

## Date
2026-04-16

## Context

The Voice-AI SFIA Skills Assessment Platform requires a real-time voice AI pipeline that can:
1. Place outbound phone calls to Australian (+61) numbers.
2. Process speech-to-text in real time.
3. Run an LLM to generate contextually relevant responses.
4. Convert responses to speech and stream them back to the caller.
5. Maintain a stateful conversation flow (Introduction → Skill Discovery → Evidence Gathering).
6. Support programmatic interjections (high-priority TTS frames interrupting normal flow).
7. Be exposed as an HTTP API for the Next.js frontend to trigger calls.

We evaluated several voice AI frameworks and telephony providers.

## Options Considered

### Voice AI Frameworks

| Framework | Language | Strengths | Weaknesses |
|-----------|----------|-----------|------------|
| **Pipecat** | Python | Purpose-built for real-time voice AI; Flows for state machines; first-class Daily integration; open source | Python-only; relatively new ecosystem |
| **Vocode** | Python | Good telephony abstractions; Twilio support | Less mature state machine support; smaller community |
| **LiveKit Agents** | Python | Strong WebRTC; good scaling story | Less focused on telephony/PSTN; no built-in flow framework |
| **Custom (WebSocket + STT + TTS)** | Any | Full control | Enormous build effort; no state management primitives |

### Telephony/WebRTC Providers

| Provider | PSTN Dial-Out | AU Region | WebRTC | Integration |
|----------|---------------|-----------|--------|-------------|
| **Daily** | Yes (SIP/PSTN) | ap-southeast-2 (Sydney) | Yes | First-class Pipecat DailyTransport |
| **Twilio** | Yes | AU presence | Via SDK | Would need custom Pipecat transport |
| **LiveKit** | Via SIP bridge | ap-southeast-2 | Yes | Would need adapter work |
| **Vonage** | Yes | AU presence | Limited | No Pipecat integration |

### API Framework

| Framework | Language | Strengths | Weaknesses |
|-----------|----------|-----------|------------|
| **FastAPI** | Python | Async-native; Pydantic validation; auto-generated OpenAPI docs; excellent for WebSocket support | Python-only (fine for voice-engine) |
| **Flask** | Python | Simple; well-known | Sync by default; less suited for WebSocket/streaming |

## Decision

### Voice AI Framework: Pipecat

Pipecat is selected because:
- **Pipecat Flows** provides a declarative state machine framework that maps directly to our assessment flow (Introduction → SkillDiscovery → EvidenceGathering).
- **Frame-based architecture** allows injecting high-priority `TTSFrame` instances for the interjection rule.
- **DailyTransport** is a first-class citizen, eliminating integration risk.
- **Pipeline composability** — STT, LLM, and TTS processors can be swapped independently (adhering to our Hexagonal Architecture).
- **UserStartedSpeaking / UserStoppedSpeaking events** give us the hooks needed for the 60-second interjection timer.

### Telephony/WebRTC: Daily

Daily is selected because:
- **`ap-southeast-2` (Sydney) region** is available, meeting our latency requirement.
- **PSTN dial-out** to Australian +61 numbers is supported.
- **Call recording** is a built-in feature (required for audit).
- **Transcript logging** can be enabled per-room.
- **Pipecat's `DailyTransport`** is the reference implementation — battle-tested.

### API Framework: FastAPI

FastAPI is selected because:
- Async-native, which aligns with Pipecat's async pipeline model.
- Pydantic models can be shared with or generated from the `packages/shared-types` JSON schemas.
- Auto-generated OpenAPI documentation makes the Next.js ↔ voice-engine contract explicit.
- WebSocket support for potential future real-time status streaming.

## Architecture

```
┌────────────────────────────────────────────────────────┐
│                  apps/voice-engine                      │
│                                                        │
│  ┌──────────────┐    ┌───────────────────────────┐    │
│  │  FastAPI      │    │  Pipecat Pipeline          │    │
│  │  /api/call    │───▶│                           │    │
│  │  /api/status  │    │  STT ─▶ LLM ─▶ TTS       │    │
│  └──────────────┘    │       ▲                    │    │
│                       │       │ RAG context        │    │
│                       │  ┌────┴──────────────┐    │    │
│                       │  │ SFIAFlowController │    │    │
│                       │  │ (Pipecat Flows)    │    │    │
│                       │  └───────────────────┘    │    │
│                       └──────────┬────────────────┘    │
│                                  │                      │
│                       ┌──────────▼────────────────┐    │
│                       │   DailyTransport           │    │
│                       │   (ap-southeast-2)         │    │
│                       └───────────────────────────┘    │
└────────────────────────────────────────────────────────┘
```

### Pipecat Pipeline Configuration

```python
pipeline = Pipeline([
    transport.input(),           # Audio from Daily
    stt_processor,               # Speech-to-Text (Deepgram/Google)
    context_aggregator.user(),   # Accumulate user context
    llm_processor,               # LLM with RAG-injected system prompt
    tts_processor,               # Text-to-Speech
    transport.output(),          # Audio back to Daily
    context_aggregator.assistant()
])
```

### State Machine (Pipecat Flows)

```
┌──────────────┐     skills identified     ┌──────────────────┐
│ Introduction │ ──────────────────────▶  │ SkillDiscovery    │
└──────────────┘                          └────────┬───────────┘
                                                   │ per skill
                                          ┌────────▼───────────┐
                                          │ EvidenceGathering  │
                                          │ (Levels 1-7 probe) │
                                          └────────┬───────────┘
                                                   │ all skills done
                                          ┌────────▼───────────┐
                                          │ Summary & Close    │
                                          └────────────────────┘
```

## Consequences

**Positive:**
- Pipecat + Daily is the lowest-risk path with proven integration.
- State machine via Pipecat Flows keeps conversation logic declarative and testable.
- Sydney region deployment gives sub-500ms latency for AU callers.
- FastAPI's OpenAPI spec can be consumed by Next.js for type-safe API calls.

**Negative:**
- Python-only voice engine means the team needs Python expertise alongside TypeScript.
- Pipecat is relatively new — breaking changes are possible in minor versions.
- Daily vendor lock-in for telephony (mitigated by VoiceTransport port abstraction).

## Compliance Notes

- All calls must be recorded with candidate consent (verbal, captured in Introduction phase).
- Recordings stored in Australian region or compliant storage.
- Daily's recording feature writes to their cloud storage; we may need to configure egress to our own S3-compatible bucket.

## Future Options (Offline & Swappable Deployment)

While the current architecture targets cloud-based deployment, the **Hexagonal Architecture** (ADR-001) enables deployment in offline or private environments with technology swaps. All substitutions are made at the **adapter layer** without changing core business logic.

### Speech-to-Text (STT) Alternatives

**Current**: Deepgram or Google Cloud STT (via Pipecat's STTProcessor)

**Offline alternatives**:
- **Whisper (OpenAI)** — Open-source, runs locally on GPU; supports 99 languages; ~1.5GB model download
- **Vosk** — Lightweight, CPU-friendly, requires training on domain-specific terms
- **Coqui STT** — Community-driven, supports multiple languages, lower accuracy than Whisper

**Swap mechanism**: Replace Pipecat's `STTProcessor` with a custom adapter wrapping the chosen STT library; the pipeline and controller remain unchanged.

### Text-to-Speech (TTS) Alternatives

**Current**: Daily's native TTS or Deepgram TTS (via Pipecat's TTSProcessor)

**Offline alternatives**:
- **gTTS (Google Text-to-Speech)** — Works offline if models are cached; multiple voices/languages
- **Pyttsx3** — 100% local, lightweight, no internet required; limited voice quality
- **Coqui TTS** — Open-source, good quality, requires model download (~500MB–2GB depending on voice)

**Swap mechanism**: Replace Pipecat's `TTSProcessor` with a custom adapter; no changes to state machine or pipeline configuration.

### LLM Alternatives

**Current**: OpenAI GPT-4 or Claude (via Pipecat's LLMProcessor)

**Offline alternatives**:
- **Ollama + Llama 2 / Mistral** — Fully local, ~4GB–13GB models, runs on CPU or GPU
- **LM Studio** — Local LLM runner with OpenAI-compatible API; easy model swapping
- **vLLM + Quantized Models** — Optimized serving for smaller models (Phi-2, TinyLlama)

**Swap mechanism**: Replace the LLMProcessor with an adapter pointing to a local model endpoint; the `SFIAFlowController` uses only the interface contract (prompt → response) and remains agnostic.

### Telephony/VoIP Alternatives

**Current**: Daily (cloud-hosted WebRTC + PSTN)

**Offline alternatives**:
- **Asterisk + FreePBX** — Self-hosted PBX; supports PSTN via carrier SIP trunk; steep learning curve
- **Kamailio** — High-performance SIP router for on-premise VoIP; requires carrier integration
- **Twilio on-premise (Flex on-premise)** — Managed alternative to self-hosting; carrier partner required
- **WebRTC-only (no PSTN)** — For internal assessments, browser-to-voice-engine WebRTC (no phone calls); uses Pipecat's default transport

**Swap mechanism**: Create a new `VoiceTransport` adapter implementing the Pipecat transport interface; swap in place of `DailyTransport` at pipeline initialization. The assessment flow logic is unchanged.

### Deployment Architecture (Offline Example)

```
┌──────────────────────────────────────────────────────┐
│         apps/voice-engine (On-Premise)               │
│                                                      │
│  ┌─────────────┐    ┌──────────────────────────┐   │
│  │  FastAPI    │    │  Pipecat Pipeline         │   │
│  │  /api/call  │───▶│                          │   │
│  └─────────────┘    │  Whisper (STT)            │   │
│                     │  ↓                        │   │
│                     │  Ollama (LLM)             │   │
│                     │  ↓                        │   │
│                     │  Coqui TTS                │   │
│                     └──────────┬─────────────────┘  │
│                                │                    │
│                     ┌──────────▼─────────────────┐  │
│                     │  Asterisk Transport        │  │
│                     │  (Local SIP/PSTN)          │  │
│                     └────────────────────────────┘  │
└──────────────────────────────────────────────────────┘
```

### Adapter Implementations Required

For offline deployment, create new adapters in `packages/adapters/src/voice-engine/`:

- `LocalWhisperSTTAdapter` — Wraps Whisper for STT
- `OllamaLLMAdapter` — Wraps Ollama's OpenAI-compatible endpoint
- `CoquiTTSAdapter` — Wraps Coqui TTS
- `AsteriskVoiceTransport` — Implements Pipecat's VoiceTransport interface for SIP/Asterisk

Each adapter:
1. Implements the Pipecat processor/transport interface
2. Handles local resource management (model downloads, GPU allocation)
3. Is instantiated at voice-engine startup via dependency injection
4. Requires no changes to `SFIAFlowController` or assessment logic

### Configuration Strategy

Use environment variables (read at startup) to select adapter implementations:

```python
# apps/voice-engine/src/index.py
stt_adapter = get_stt_adapter(STT_PROVIDER)  # "deepgram" | "whisper" | "vosk"
tts_adapter = get_tts_adapter(TTS_PROVIDER)  # "daily" | "coqui" | "pyttsx3"
llm_adapter = get_llm_adapter(LLM_PROVIDER)  # "openai" | "ollama" | "lm-studio"
voice_transport = get_transport(TRANSPORT_TYPE)  # "daily" | "asterisk" | "webrtc-only"
```

This allows the same codebase to run in cloud or offline environments without recompilation.
