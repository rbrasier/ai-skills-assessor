# Speech-to-Text Solutions: Detailed Technical Comparison

**Date**: May 13, 2026
**Status**: Research Complete
**Purpose**: Comprehensive technical comparison of STT solutions for offline, self-hosted voice assessment platform

---

## 1. Pipecat Built-In Whisper / Faster-Whisper

### Audio Format Handling
| Property | Spec |
|----------|------|
| **Input Sample Rate** | Any (Pipecat resamples to 16 kHz) |
| **Output Sample Rate** | 16 kHz (Whisper standard) |
| **Bit Depth** | 16-bit signed PCM (int16) |
| **Channels** | Mono (Pipecat downmixes stereo if needed) |
| **Frame Size** | Buffered until VAD detects silence (~512 samples at a time) |
| **Encoding** | Raw PCM (no compression) |

### Processing Pipeline
```
Daily WebRTC Transport
    ↓ (AudioRawFrame, 16-bit mono PCM)
Pipecat SegmentedSTTService
    ↓ VAD (Silero VAD built-in)
    ↓ Collect audio until silence detected (2-3 sec default)
Faster-Whisper (CTranslate2)
    ↓ Inference (batch processing)
TranscriptionFrame + InterimTranscriptionFrame
```

### Resource Requirements
| Metric | `tiny.en` | `base.en` | `small.en` | `large-v3` |
|--------|-----------|-----------|-----------|-----------|
| **Model Size** | 39 MB | 74 MB | 244 MB | 1.5 GB |
| **Memory (model + inference)** | 256 MB | 512 MB | 1 GB | 3+ GB |
| **CPU (single 16s utterance)** | 2-3 sec | 1-2 sec | 500ms | 200ms |
| **Quantized (int8)** | 100 MB | 200 MB | 600 MB | 1.2 GB |
| **WER (accuracy)** | 8-10% | 7.5% | 7% | 7.4% |
| **Max Concurrent** | 10+ per 2-core CPU | 5-8 | 2-3 | 1-2 (CPU) |

### NaN Corruption Handling
**Root cause**: Not applicable — Pipecat's frame system validates audio before passing to Whisper
**NaN detection**: Pipecat's `AudioRawFrame` expects valid int16 PCM; framework-level validation
**Corruption recovery**: No sanitization needed; proper audio format enforced upstream
**Floating-point conversion**: Whisper internally converts int16 → float32 [-1.0, 1.0] using numerically stable division

### Accuracy (Word Error Rate - WER)
| Language | Model | WER | Note |
|----------|-------|-----|------|
| English (clean) | Large V3 | 7.4% | Reference: 680k hours multilingual training |
| English (noisy) | Large V3 | 12-15% | Phone audio, background noise |
| English (clean) | Distil-Whisper | 6.3% | Knowledge distillation from Large V3 |
| English (accented) | Large V3 | 10-12% | Non-native speakers |
| Multilingual (99 languages) | Large V3 | 8-15% (avg) | Varies by language quality |

### Latency Breakdown (Whisper Large V3 on CPU)
```
User speaks for 5 seconds
    ↓ (5 sec)
VAD detects silence
    ↓ (200ms)
Audio buffered to Whisper
    ↓ (0ms)
Inference starts
    ↓ (5-8 seconds on 2-core CPU)
TranscriptionFrame emitted
    ↓ (0ms)
Frame processed by LLM
```
**Total latency**: ~10-13 seconds (acceptable for turn-taking dialogue)
**Interim results**: None (batch model)

### Known Issues & Mitigations
| Issue | Severity | Mitigation |
|-------|----------|-----------|
| **Hallucinations** ("transcribing silence") | Medium | Set `no_speech_prob > 0.4` to filter |
| **Out-of-memory** on large models | High | Use smaller model or reduce batch size |
| **Poor performance on low-SNR audio** | Medium | Pre-process with noise suppression |
| **Model download on first run** | Low | Cache models in container/image |
| **No streaming** (batch only) | Design choice | Acceptable for turn-based interviews |
| **Language detection errors** | Low | Explicitly set `language="en"` if known |

### Integration with Pipecat Flow
```python
from pipecat.services.whisper.stt import WhisperSTTService
from pipecat.pipelines.pipeline import Pipeline

stt_service = WhisperSTTService(
    model="small.en",  # Balance accuracy + speed
    language="en",
    device="cpu",  # or "cuda", "auto"
    compute_type="int8",  # Quantization
    no_speech_prob=0.4,  # Filter hallucinations
    vad_threshold=0.5,  # Silero VAD sensitivity
)

pipeline = Pipeline([
    transport,  # Daily WebRTC
    stt_service,  # ← Emits TranscriptionFrame
    llm_service,
    tts_service,
    transport,
])
```

---

## 2. Distil-Whisper (English-Only Optimization)

### Technical Details
- **Architecture**: Knowledge-distilled from Whisper Large V3 using 1% of the training data
- **Model size**: 756M parameters (vs. 1.54B for Large V3)
- **Training approach**: Matched generation and sequence-level knowledge distillation
- **Performance**: 6x faster than Large V3 while maintaining ~1% WER difference

### Resource Requirements (Compared to Whisper)
| Metric | Whisper Large V3 | Distil-Whisper | Improvement |
|--------|------------------|-----------------|-------------|
| **Model size** | 1.5 GB | 756 MB | 50% smaller |
| **Inference time (16s audio)** | 8 sec | 1.3 sec | 6x faster |
| **Memory required** | 3 GB | 1.5 GB | 50% less |
| **WER** | 7.4% | 6.3% | 1.1% better |
| **Max concurrent (4-core CPU)** | 2 | 6+ | 3x more capacity |

### Use Cases
✅ **Ideal for**:
- English-only assessments
- Cost-optimized deployments with tight CPU budgets
- High-throughput scenarios (many concurrent interviews)
- ARM64 edge devices (e.g., Graviton processors)

❌ **Not suitable for**:
- Multilingual interviews
- Interview recordings with code/technical terms (English terms may still be in Large V3 training)
- Situations where the 1% WER difference is critical

### Integration (Same as Whisper)
```python
stt_service = WhisperSTTService(
    model="distil-medium.en",  # Distilled variant
    language="en",
    device="cpu",
)
```

---

## 3. NVIDIA NeMo ASR (Parakeet + Nemotron)

### Architecture: Streaming Transducer
- **Model**: Parakeet RNN-Transducer (1.1B parameters)
- **Framework**: PyTorch, NVIDIA NeMo toolkit
- **Inference**: NVIDIA TensorRT for optimization
- **Latency**: 160ms chunk processing (streaming)

### Audio Handling
| Property | Spec |
|----------|------|
| **Chunk size** | 160ms @ 16 kHz = 2560 samples |
| **Streaming window** | 16 mel frames per chunk |
| **State management** | Encoder/decoder cache maintained across chunks |
| **Output latency** | ~320ms (2 chunks: processing + downstream) |
| **Final latency** | Immediate after user stops speaking |

### Resource Requirements
| Component | Requirement | Note |
|-----------|-------------|------|
| **Model size** | 2.4 GB | Nemotron-Speech-Streaming-0.6B |
| **Memory (GPU)** | 6-8 GB | Batch size 1-4 on RTX 4070 |
| **Memory (CPU)** | 4+ GB | Very slow CPU inference |
| **Compute type** | FP16 (recommended) | INT8 for reduced memory |
| **Throughput** | ~200x real-time on A100 | Streaming chunks |

### Accuracy (Parakeet Models)
| Dataset | Accuracy (WER) | Model |
|---------|--------|-------|
| LibriSpeech test-clean | 5.85% | Parakeet 1.1B |
| LibriSpeech test-other | 9.2% | Parakeet 1.1B |
| Common Voice (accented) | 8-10% | Parakeet 1.1B |

### Latency Profile (vs. Batch Whisper)
```
User speaks: "Hello, how are you today?"
    (160ms chunk 1)       → Interim: "Hello"
    (160ms chunk 2)       → Interim: "Hello how"
    (160ms chunk 3)       → Interim: "Hello how are"
    (160ms chunk 4)       → Interim: "Hello how are you"
    (160ms chunk 5)       → Interim: "Hello how are you today"
    (160ms silence chunk)  → Final: "Hello how are you today"
Total: ~1-1.5 seconds for interim transcription to appear
```

### Pipecat Integration Status
**Status**: Not natively integrated as of May 2026
**Options**:
1. Use NVIDIA's reference Pipecat adapter (if available in `nemotron-january-2026` repo)
2. Build custom `FrameProcessor` (similar complexity to WhisperLive adapter)

```python
# Hypothetical integration (may differ from actual API)
from pipecat.services.nemo.stt import NeMoSTTService

stt_service = NeMoSTTService(
    model="parakeet-1.1b",
    device="cuda",
    batch_size=1,
)
```

### When to Use
✅ **Best for**:
- Applications requiring real-time streaming (interim transcription visible to user)
- High-accuracy English-focused assessments
- GPU-available infrastructure (DGX, A100, RTX 4090)
- Low-latency requirements (<500ms)

❌ **Not ideal for**:
- CPU-only deployments (too slow)
- Cost-constrained environments
- Turn-based dialogue where batch latency acceptable
- Multilingual interviews (English-focused)

---

## 4. Moonshine (Edge-Optimized Streaming)

### Architecture: Ergodic Streaming Encoder
- **Model size**: 27 MB (smallest; ultra-lightweight)
- **Inference**: Real-time streaming with minimal latency
- **Framework**: PyTorch, optimized for CPU/edge

### Audio Handling
| Property | Spec |
|----------|------|
| **Chunk size** | 16 ms (smallest supported) |
| **Streaming window** | Single-pass encoder (no lookahead) |
| **Output latency** | 16-50ms per chunk |
| **Memory** | ~50 MB RAM during inference |
| **Model variants** | 27 MB, 110 MB, 350 MB (English only) |

### Resource Requirements
| Metric | Moonshine | Whisper Tiny | Ratio |
|--------|-----------|-------------|-------|
| **Model size** | 27 MB | 39 MB | 69% |
| **Memory required** | 50 MB | 256 MB | 20% |
| **Inference time (10s)** | 50ms | 2-3 sec | 60x faster |
| **Accuracy (WER)** | 10-12% | 8-10% | Slightly worse |
| **Typical latency** | 50ms | 5-6 sec | 100x lower |

### Accuracy
| Test Set | WER | Note |
|----------|-----|------|
| LibriSpeech test-clean | 8.1% | Larger model (350 MB) |
| LibriSpeech test-other | 14.2% | Noisy speech |
| Common Voice | 10-12% | Mixed accent/background |
| Phone audio (assessment scenario) | 12-16% (est) | Not officially tested |

### Pipecat Integration
**Status**: Not natively integrated
**Effort**: Custom `FrameProcessor` required (similar to WhisperLive)
**Example**:
```python
# Pseudocode for custom adapter
class MoonshineFrameProcessor(FrameProcessor):
    def __init__(self):
        self.model = MoonshineASR.load("moonshine_base")

    async def process_frame(self, frame: AudioRawFrame):
        result = self.model.transcribe_streaming(frame.audio)
        await self.push_frame(InterimTranscriptionFrame(text=result))
```

### When to Use
✅ **Best for**:
- Extreme resource constraints (Raspberry Pi, embedded devices)
- Real-time streaming requirements with minimal latency
- Very low-power deployments (battery-powered devices)
- Cold-start performance critical

❌ **Not suitable for**:
- High-accuracy transcription (10-12% WER too high for assessment)
- Production interview transcripts (unacceptable error rate)
- This project (accuracy requirement overrides latency benefit)

---

## 5. Vosk (Kaldi-Based Streaming)

### Architecture: Kaldi Decoder
- **Framework**: Kaldi speech recognition toolkit (legacy)
- **Model**: HMM (Hidden Markov Model) based
- **Streaming**: True real-time processing
- **Languages**: 20+ language models

### Audio Handling
| Property | Spec |
|----------|------|
| **Sample rate** | 8 kHz, 16 kHz (model-dependent) |
| **Chunk size** | Flexible (processes as it arrives) |
| **Output latency** | 50-200ms per utterance |
| **Buffer requirements** | Minimal (~1 MB) |

### Resource Requirements
| Metric | Value | Note |
|--------|-------|------|
| **Model size** | 50-150 MB | Very small |
| **Memory** | 100-300 MB | Runtime |
| **CPU usage** | <1 core | Minimal |
| **Suitable devices** | Raspberry Pi, IoT | Edge-friendly |

### Accuracy
| Dataset | WER | Note |
|---------|-----|------|
| WSJ (clean) | 12-15% | Kaldi acoustic models |
| Phone/noisy | 20-30% | Poor on background noise |
| Assessment audio (est) | 20-35% | Unacceptable |

### Known Issues
1. **Vocabulary limitations**: Works best with small, pre-defined vocabularies
2. **Poor generalization**: Struggles with conversational speech, accents, proper nouns
3. **No modern NLP**: HMM-based models can't learn contextual dependencies
4. **Maintenance**: Last major update 2015 (Kaldi academic project)
5. **Language support**: English models adequate but outdated

### Pipecat Integration
**Status**: Not integrated
**Effort**: Custom adapter required
**Assessment**: Low priority (poor accuracy for this use case)

---

## 6. Coqui STT (Formerly Mozilla DeepSpeech)

### Status: DISCONTINUED
- **Last major update**: 2023 (ceased development)
- **Cloud services**: Shut down
- **Repository**: Still available but unmaintained

### Historical Architecture
- **Framework**: TensorFlow-based
- **Models**: Acoustic models trained on Mozilla Common Voice
- **Language**: Primarily English
- **Accuracy**: 8-12% WER (outdated)

### Why Not Recommended
1. **No security updates** since 2023
2. **Dependency rot**: TensorFlow/CUDA version incompatibilities
3. **Build failures**: Fragile setup with older Python versions
4. **Poor accuracy**: Falls behind modern alternatives
5. **Community support**: Minimal; no active maintenance

### Risk Assessment
| Risk | Severity |
|------|----------|
| **Security vulnerabilities** | High |
| **Incompatibility with new OS/Python** | High |
| **Model accuracy outdated** | Medium |
| **Build/deployment issues** | High |

---

## 7. Julius (Academic Speech Recognition Engine)

### Architecture: Large Vocabulary Continuous Speech Recognition (LVCSR)
- **Framework**: Academic research platform (Kyoto University)
- **Models**: Two-pass decoder (first pass: fast; second pass: precise)
- **Languages**: Primarily Japanese; English models from VoxForge (community)

### Audio Handling
| Property | Spec |
|----------|------|
| **Sample rate** | 8 kHz, 16 kHz |
| **Format** | WAV, RAW PCM |
| **Processing** | Real-time streaming |
| **Latency** | 100-300ms |

### Resource Requirements
| Metric | Value |
|--------|-------|
| **Memory** | 32-64 MB (very low) |
| **Model size** | 50-300 MB |
| **CPU usage** | <50% single core |
| **Platforms** | Linux, Windows, embedded |

### Accuracy
| Model | Language | WER |
|-------|----------|-----|
| Julius JP | Japanese | 3-5% |
| VoxForge EN | English | 15-25% |

**Issue**: English models from community (VoxForge) are outdated, with poor accuracy on modern speech

### Pipecat Integration
**Status**: Not integrated
**Assessment**: Low priority (poor English accuracy)

---

## 8. CMU PocketSphinx (Legacy CMU Sphinx)

### Architecture: HMM-Based Decoder (1970s-1990s Algorithms)
- **Framework**: CMU Sphinx suite
- **Models**: Legacy acoustic models, outdated
- **Status**: Maintenance mode (occasional bug fixes only)

### Resource Requirements
| Metric | Value |
|--------|-------|
| **Model size** | 10-50 MB |
| **Memory** | 50-100 MB |
| **CPU** | Minimal |
| **Devices** | Raspberry Pi, embedded |

### Accuracy
| Scenario | WER |
|----------|-----|
| Clean speech | 25-30% |
| Noisy speech | 35-50% |
| Accented speech | 40%+ |

**Verdict**: Unacceptable accuracy for any real-world assessment transcription

### Why Not Recommended
1. **Ancient algorithms**: HMM technology from 1970s-1990s
2. **Poor accuracy**: 25-50% WER (50%+ worse than Whisper)
3. **No active development**: Maintenance-only mode
4. **Limited language support**: Mostly outdated English
5. **Academic only**: Not suitable for production systems

---

## Comparative Performance Table

| Feature | Pipecat Whisper | Distil-Whisper | NeMo | Moonshine | Vosk | Coqui | Julius | PocketSphinx |
|---------|---|---|---|---|---|---|---|---|
| **Accuracy (WER)** | 7.4% | 6.3% | 5.85% | 10-12% | 20%+ | 8-12% | 15%+ | 25-50% |
| **Latency** | 5-6s | 1-2s | 320ms | 50ms | 200ms | Variable | 100-300ms | 100ms |
| **Model Size** | 1.5GB | 756MB | 2.4GB | 27MB | 100MB | 200MB | 50-300MB | 10-50MB |
| **Memory** | 3GB | 1.5GB | 6-8GB | 50MB | 200MB | 500MB | 64MB | 100MB |
| **CPU** | ✅ | ✅✅ | ❌ GPU | ✅✅ | ✅✅✅ | ⚠️ | ✅✅ | ✅✅✅ |
| **Streaming** | ❌ | ❌ | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ |
| **Pipecat Native** | ✅✅✅ | ✅✅✅ | ⚠️ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Production-Ready** | ✅✅✅ | ✅✅✅ | ✅✅ | ⚠️ | ⚠️ | ❌ | ⚠️ | ❌ |
| **Maintenance** | Active | Active | Active | Active | Stagnant | Dead | Stagnant | Minimal |
| **Overall Score** | **9/10** | **9/10** | **8/10** | **6/10** | **4/10** | **2/10** | **3/10** | **1/10** |

---

## Audio Quality & Assessment Considerations

### Phone Audio Characteristics (Real Interviews)
```
Typical interview audio:
- Bandwidth: 300 Hz - 3.4 kHz (narrowband, phone quality)
- Noise: 50-70 dB SPL background (office, road noise)
- Artifacts: Echo, compression, variable volume levels
- Sample rate: Often 8 kHz (lower fidelity than 16 kHz)
```

### Performance Degradation on Phone Audio
| Model | Clean (LibriSpeech) | Phone Audio (Est) | Degradation |
|-------|------------|-------------|-------------|
| Whisper Large V3 | 7.4% | 12-15% | ~2x |
| Distil-Whisper | 6.3% | 11-13% | ~2x |
| NeMo Parakeet | 5.85% | 10-12% | ~2x |
| Moonshine | 10% | 15-18% | ~1.5x |
| Vosk | 20% | 30-40% | ~2x |

### Mitigation Strategies
1. **Noise suppression**: Pre-process audio with VAD + noise reduction
2. **Model fine-tuning**: Train on domain-specific assessment audio
3. **Confidence thresholding**: Flag low-confidence transcriptions for SME review
4. **Speaker diarization**: Identify interviewer vs. candidate for context
5. **Keyword/entity extraction**: Validate key terms (skills, job titles) separately

---

## Deployment Checklist

### For Pipecat Whisper
- [ ] CPU supports AVX2 (SIMD acceleration for CTranslate2)
- [ ] Disk: 2-3 GB free for model downloads
- [ ] RAM: 2 GB minimum for `small.en` model
- [ ] Network: Internet for first-run model download only
- [ ] Test with actual interview audio (phone/background noise)
- [ ] Tune `no_speech_prob` threshold for hallucination filtering
- [ ] Monitor OOM (out-of-memory) errors under load
- [ ] Set up model caching in container/image to avoid re-download

### For NeMo Parakeet (if chosen)
- [ ] GPU: RTX 4070+ or A100 for practical latency
- [ ] CUDA: 12.0+ for TensorRT optimization
- [ ] Memory: 8 GB VRAM minimum
- [ ] Framework: PyTorch 2.0+ for efficient inference
- [ ] Separate container for ASR service (like WhisperLive pattern)
- [ ] Health checks on ASR port
- [ ] Load testing for concurrent calls

---

## References & Sources

1. **Pipecat Documentation**
   - [Whisper STT Service](https://docs.pipecat.ai/server/services/stt/whisper)
   - [Speech-to-Text Services Overview](https://docs.pipecat.ai/pipecat/learn/speech-to-text)

2. **Model Papers & Benchmarks**
   - Whisper: [Robust Speech Recognition via Large-Scale Weak Supervision](https://arxiv.org/abs/2212.04356)
   - Distil-Whisper: [Distil-Whisper: Robust Knowledge Distillation via Speech Recognition Task-Oriented Learning](https://arxiv.org/abs/2311.01541)
   - Moonshine: [Moonshine: A Lightweight Streaming ASR Model](https://arxiv.org/abs/2602.12241)
   - Parakeet: [NVIDIA Parakeet: Self-Supervised Training for Speech Recognition](https://arxiv.org/abs/2204.03100)

3. **Benchmarks & Comparisons**
   - [Northflank: Best Open Source Speech-to-Text Models 2026](https://northflank.com/blog/best-open-source-speech-to-text-stt-model-in-2026-benchmarks)
   - [Modal: Choosing Between Whisper Variants](https://modal.com/blog/choosing-whisper-variants)
   - [Hugging Face Open ASR Leaderboard](https://huggingface.co/spaces/hf-audio/open_asr_leaderboard)

4. **Codebase References**
   - [ADR-007: WhisperLive STT Service](./ADR-007-whisperlive-stt-service.md)
   - [Current WhisperSTTService Adapter](../../../apps/voice-engine/src/adapters/stt/whisper_stt_service.py)

---

## Decision Framework

**Choose this if...**

| Scenario | Recommendation |
|----------|---|
| Need highest accuracy + CPU-friendly | **Pipecat Whisper Large V3** |
| English-only interviews + cost optimization | **Distil-Whisper** |
| Real-time streaming requirement + GPU available | **NVIDIA NeMo** |
| Extreme resource constraints (edge) | **Moonshine** |
| Smallest possible footprint | **Moonshine 27 MB** |
| Academic research/prototyping | **Julius** (with caveats) |
| None of the above | **Reconsider use case** |

---

**End of Technical Comparison Document**
