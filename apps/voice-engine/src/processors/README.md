# Audio Chunking & Streaming LLM Responses

## Overview

This processor solves the latency problem in voice interactions:

**Without chunking:**
```
User speaks (15s) → STT processes all (8s) → LLM responds (4s) → TTS (3s) → User hears (30s latency)
```

**With chunking:**
```
User speaks 5s → STT (2s) → LLM #1 queued
User speaks 5s → STT (2s) → LLM #2 queued
User speaks 5s → STT (2s) → LLM #3 queued
User stops → Play LLM #3 (3s) → User hears (8s latency)
    ↓ background
Full transcript finalized for record
```

## Architecture

### 1. AudioChunkingProcessor
**File:** `audio_chunking_processor.py`

Buffers audio into 5-second chunks, emits for STT, and tracks LLM responses.

```python
chunker = AudioChunkingProcessor(chunk_duration_s=5.0)

# Push audio frames
chunker.push_audio_frame(audio_bytes, sample_rate=16_000)

# Register callbacks
chunker.register_stt_complete(async def on_stt(transcription): ...)
chunker.register_llm_ready(async def on_llm(response): ...)
chunker.register_speech_ended(async def on_speech_ended(transcript): ...)

# VAD integration
chunker.handle_vad_frame(is_speech=True/False, energy_db=-50.0)

# Get results
response = chunker.get_latest_response()  # LLMResponse for playback
transcript = chunker.get_full_transcript()  # Full transcript for record
```

### 2. PipecatAudioChunker
**File:** `pipecat_audio_chunker.py`

Wraps AudioChunkingProcessor as a Pipecat FrameProcessor for pipeline integration.

```python
chunker = build_audio_chunking_frame_processor(chunk_duration_s=5.0)
pipeline.add_before(stt_processor, chunker)
```

**Frame flow:**
- Consumes: `AudioRawFrame`
- Produces: (internally buffers, doesn't emit audio downstream)
- Consumes: `TranscriptionFrame` from STT
- Internally queues LLM responses

### 3. FasterWhisperChunkedSTT
**File:** `adapters/stt/faster_whisper_chunked_stt.py`

Local Faster-Whisper model for on-device transcription.

```python
stt = FasterWhisperChunkedSTTService(model_name="tiny.en").build()
```

**Advantages over WhisperLive:**
- No external process/container needed
- Runs locally (GPU or CPU)
- Lower latency (~500ms-2s per chunk)
- No WebSocket/network overhead

## Usage

### Option A: Full Pipeline Integration

See `integration_example.py` for complete pipeline setup:

```python
pipeline = await build_chunked_pipeline(
    llm_provider=anthropic_provider,
    tts_service=tts_service,
    transport=daily_transport,
)
```

### Option B: Standalone Demo

```bash
cd apps/voice-engine
python -m src.processors.demo_chunking
```

Output shows:
- Segments being buffered
- STT completion for each
- LLM responses queued
- Speech end detection
- Final transcript

### Option C: Custom Integration

```python
from src.processors.audio_chunking_processor import AudioChunkingProcessor
from src.adapters.stt.faster_whisper_chunked_stt import FasterWhisperChunkedSTTService

# Create chunker
chunker = AudioChunkingProcessor(chunk_duration_s=5.0)

# Create STT
stt = FasterWhisperChunkedSTTService(model_name="tiny.en")

# In your processing loop:
for audio_frame in incoming_audio:
    chunker.push_audio_frame(audio_frame.audio, audio_frame.sample_rate)

    # When segment is ready (internally buffered):
    # → STT processes it
    # → STT emits TranscriptionFrame
    # → chunker receives and queues LLM response
    # → track latest response

# When user stops talking:
response = chunker.get_latest_response()
await tts.synthesize(response.text)

# For the assessment record:
transcript = chunker.get_full_transcript()
await persistence.store_transcript(transcript)
```

## Configuration

### Chunk Duration
```python
chunker = AudioChunkingProcessor(chunk_duration_s=5.0)
```
- Larger (10s): Fewer chunks, higher latency, better context
- Smaller (3s): More chunks, lower latency, less context

### Sample Rate
```python
chunker = AudioChunkingProcessor(sample_rate=16_000)
```
Standard: 16 kHz (16,000 samples/second)

### VAD (Voice Activity Detection)
```python
chunker = AudioChunkingProcessor(
    silence_duration_s=0.8,  # seconds of silence to trigger end-of-speech
    silence_threshold_db=-40.0,  # energy threshold
)
```

## Data Flow

```
AudioRawFrame (streaming)
    ↓
AudioChunkingProcessor (buffers 5s)
    ↓ [5s accumulated]
AudioRawFrame (buffered chunk)
    ↓
FasterWhisperSTT (async transcription)
    ↓ [transcription complete]
TranscriptionFrame
    ↓
AudioChunkingProcessor (consumes, queues LLM)
    ↓ [internally: LLM response prepared]
[tracked as latest response]
    ↓
VADFrame (silence detected)
    ↓
[callback: speech_ended]
    ↓
Use latest response for TTS output
Use full transcript for assessment record
```

## Example: 15-second Speech

```
Timeline:
t=0-5s:   User: "Hello, my name is Alice and I specialize in Python"
          → Segment 1 queued to STT

t=5-10s:  User: "I have 8 years of experience"
          → Segment 1 STT done → LLM response #1 queued
          → Segment 2 queued to STT

t=10-15s: User: "including cloud architecture and DevOps"
          → Segment 2 STT done → LLM response #2 queued
          → Segment 3 queued to STT

t=15s:    User stops (VAD detects 0.8s silence)
          → Segment 3 STT done → LLM response #3 queued
          → Speech ended event fired

t=15-18s: Play LLM response #3 to user
          → Background: finalize transcript for record

Result:
- User heard response 8s after stopping (vs 30s without chunking)
- Full transcript available for assessment
```

## Files

| File | Purpose |
|------|---------|
| `audio_chunking_processor.py` | Core buffering & LLM queueing logic |
| `pipecat_audio_chunker.py` | Pipecat frame processor wrapper |
| `adapters/stt/faster_whisper_chunked_stt.py` | Local Faster-Whisper STT |
| `integration_example.py` | Full pipeline example |
| `demo_chunking.py` | Standalone demo/test |
| `README.md` | This file |

## Next Steps

1. **Install faster-whisper:**
   ```bash
   pip install faster-whisper
   ```

2. **Test with demo:**
   ```bash
   python -m src.processors.demo_chunking
   ```

3. **Integrate into pipeline:**
   - Modify `bot_runner.py` to use `build_chunked_pipeline()`
   - OR manually add chunker before STT in existing pipeline

4. **Configure for your use case:**
   - Adjust chunk duration (5s optimal for assessment interviews)
   - Tune VAD silence threshold
   - Select Faster-Whisper model size (tiny.en for speed, base/small for accuracy)

## Performance Notes

### Faster-Whisper Model Sizes
- `tiny.en`: ~39MB, ~200ms per 5s chunk (GPU), ~1.5s (CPU)
- `base.en`: ~140MB, ~300ms per 5s chunk (GPU), ~3s (CPU)
- `small.en`: ~483MB, ~600ms per 5s chunk (GPU), ~6s (CPU)

### Recommended Setup
- **GPU (T4+):** tiny.en or base.en
- **CPU:** tiny.en only
- **Assessment interviews:** 5-second chunks, tiny.en model

### Latency Breakdown (Example)
```
User speech:       0-5s
STT processing:    2s (tiny.en on GPU)
LLM generation:    1-2s (Claude Haiku)
TTS synthesis:     2-3s (ElevenLabs)
─────────────────────
Total latency:     7-9s (vs 20-30s without chunking)
```
