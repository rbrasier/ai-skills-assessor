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
