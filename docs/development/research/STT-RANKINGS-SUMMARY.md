# STT Alternatives: Quick Ranking Summary

## Tier 1: Recommended ✅

### 1️⃣ Pipecat Built-In Whisper/Faster-Whisper (BEST CHOICE)
- **Accuracy**: 7.4% WER (Large V3) / 6.3% WER (Distil-Whisper)
- **Integration**: Native Pipecat service — no custom adapter needed
- **Latency**: 5-6 second batch (acceptable for turn-taking interviews)
- **CPU**: 2-core systems can handle `tiny.en`; 4-core for `small`
- **Offline**: Yes, fully offline after model download
- **Maintenance**: Pipecat core — actively updated
- **Why choose**: Eliminates WhisperLive's NaN corruption issue, no external service, simplest integration
- **Migration effort**: 1 week

### 2️⃣ Distil-Whisper (via Pipecat)
- **Accuracy**: 6.3% WER (within 1% of Large V3)
- **Speed**: 6x faster than Whisper Large V3
- **Model size**: 756 MB (vs. 1.5 GB for Large V3)
- **Language**: English only
- **Why choose**: Best CPU performance when accuracy matters; cost optimization
- **Same migration**: Uses Pipecat Whisper service (no additional work)

---

## Tier 2: Alternative Options (if requirements change) ⚠️

### 3️⃣ NVIDIA NeMo/Parakeet ASR
- **Accuracy**: 5.85% WER (highest among open source)
- **Latency**: 160ms streaming (real-time interim results)
- **Integration**: Available but requires custom adapter or NVIDIA reference implementation
- **GPU required**: Practical performance needs GPU; CPU fallback possible but slower
- **Offline**: Yes
- **Why useful**: If real-time streaming becomes required; enterprise-backed
- **When to consider**: Only if stakeholders demand "interim transcription" while user speaks
- **Migration effort**: 2 weeks (custom integration)

---

## Tier 3: Not Recommended ❌

### 4️⃣ Moonshine
- **Accuracy**: 10-12% WER (too low for detailed transcription)
- **Latency**: 50ms streaming (excellent)
- **Model size**: 27 MB (ultra-lightweight)
- **Use case**: Edge devices, extreme resource constraints
- **Why not**: Accuracy unacceptable for assessment transcripts; requires custom adapter
- **Score**: 6/10

### 5️⃣ Vosk
- **Accuracy**: 15-25% WER (unacceptable)
- **Latency**: <100ms streaming
- **Use case**: Keyword spotting, command recognition only
- **Why not**: Outdated Kaldi models, poor accuracy, requires custom adapter
- **Score**: 4/10

### 6️⃣ Coqui STT
- **Accuracy**: 8-12% WER
- **Status**: DISCONTINUED (late 2023) — no active maintenance
- **Why not**: Dead project, security risk, incompatibilities inevitable
- **Score**: 2/10

### 7️⃣ Julius
- **Accuracy**: 10-15% WER
- **Status**: Stable but minimal updates; academic project
- **Why not**: Limited English models, no Pipecat integration, poor accuracy
- **Score**: 3/10

### 8️⃣ CMU PocketSphinx
- **Accuracy**: 25-35% WER (terrible)
- **Status**: Maintenance mode only
- **Why not**: Ancient algorithms (1970s-1990s), unusable accuracy
- **Score**: 1/10

---

## Decision Matrix for Your Use Case

**Requirements**: Offline, self-hosted, compatible with Pipecat, reliable for voice assessments

| Requirement | Pipecat Whisper | Distil-Whisper | NeMo | Moonshine | Vosk | Others |
|---|---|---|---|---|---|---|
| **Offline** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Pipecat native** | ✅ | ✅ | ⚠️ | ❌ | ❌ | ❌ |
| **Accuracy** | ✅ (7.4%) | ✅ (6.3%) | ✅ (5.85%) | ❌ (10-12%) | ❌ (15-25%) | ❌ |
| **CPU-friendly** | ✅ | ✅✅ | ⚠️ (GPU) | ✅✅ | ✅✅✅ | Varies |
| **Production-ready** | ✅✅✅ | ✅✅✅ | ✅✅ | ⚠️ | ⚠️ | ❌ |
| **Streaming** | ❌ (batch) | ❌ (batch) | ✅ | ✅ | ✅ | Varies |

---

## The NaN Audio Corruption Issue

**Root Cause**: WhisperLive's WebSocket protocol or audio frame handling occasionally produces invalid float values (NaN) in the audio pipeline.

**Current Workaround** (in `whisper_stt_service.py`):
```python
def _ensure_int16_pcm(audio: bytes) -> bytes:
    # Detects NaN and Inf values, replaces with 0
    nan_count = np.isnan(float_samples).sum()
    inf_count = np.isinf(float_samples).sum()
    if nan_count > 0 or inf_count > 0:
        # Replace NaN/Inf with valid values
        float_samples = np.nan_to_num(...)
```

**Why Pipecat Whisper solves this**:
- No external WebSocket service, no protocol conversion step
- Audio frames flow directly from Daily transport → Pipecat's audio frame → Whisper
- Pipecat's frame handling already validates and normalizes audio
- Eliminates the conversion layer where NaN corruption occurs

---

## Quick Checklist: Switch to Pipecat Whisper

**Can we do this?**
- ✅ Remove `websockets` dependency (already not in core requirements)
- ✅ Remove external WhisperLive container management
- ✅ Delete custom `WhisperSTTService` adapter
- ✅ Use Pipecat's built-in `WhisperSTTService`
- ✅ Update environment variables (one change)
- ✅ Re-test with actual interview audio

**Effort**: 1 week
**Risk**: Low (Pipecat's Whisper is battle-tested)
**Benefit**: Eliminates NaN issue, simpler code, maintained by Pipecat team

---

## Final Recommendation

🏆 **Switch to Pipecat's Built-In Whisper Service**

**Rationale**:
1. Solves the NaN audio corruption issue by removing the WebSocket layer
2. Reduces operational complexity (no external container)
3. No new integrations needed (Pipecat already uses Faster-Whisper internally)
4. Maintains 7.4% WER accuracy (competitive with industry)
5. Proven stable in production Pipecat deployments
6. Easier to maintain going forward
7. Enables future migration to streaming models (Parakeet) if requirements change

**Next Steps**:
1. Create ADR-008 documenting the migration
2. Run proof-of-concept with Pipecat Whisper
3. Compare transcript quality with current WhisperLive baseline
4. Plan 1-week sprint for implementation

---

## Sources

- [Pipecat: Whisper STT Service](https://docs.pipecat.ai/server/services/stt/whisper)
- [AssemblyAI: Top 8 Open Source STT Options for Voice Applications](https://www.assemblyai.com/blog/top-open-source-stt-options-for-voice-applications)
- [Northflank: Best Open Source Speech-to-Text STT Model in 2026 (with benchmarks)](https://northflank.com/blog/best-open-source-speech-to-text-stt-model-in-2026-benchmarks)
- [Modal: Choosing Between Whisper Variants](https://modal.com/blog/choosing-whisper-variants)
- [Local AI Master: Faster-Whisper Setup Guide 2026](https://localaimaster.com/blog/faster-whisper-guide)
- [Current codebase ADR-007](./ADR-007-whisperlive-stt-service.md)
