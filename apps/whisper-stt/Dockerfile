# apps/whisper-stt/Dockerfile
# CPU-only faster-whisper + Silero VAD — deployable on Railway Hobby (no GPU).
#
# Build context: repo root
#   docker build -f apps/whisper-stt/Dockerfile -t whisper-stt .
#
# Memory recommendation: 4 GB (Railway: set service memory limit to 4096 MB)
# The tiny.en model is ~75 MB on disk and fits comfortably in 512 MB RAM, but
# torch + numpy overhead means 4 GB headroom is safe for concurrent connections.

FROM python:3.11-slim

# ffmpeg is required by faster-whisper for audio decoding (WAV/PCM path skips
# it, but having it installed avoids hard crashes on future format support).
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps before copying source so Docker cache is preserved when
# only application code changes.
COPY apps/whisper-stt/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY apps/whisper-stt/main.py ./main.py

# Pre-download the model during build so Railway deploys start instantly.
# Set WHISPER_MODEL to a different size via ARG if needed (tiny.en is ~75 MB).
ARG WHISPER_MODEL=tiny.en
ENV WHISPER_MODEL=${WHISPER_MODEL}
RUN python - <<'EOF'
from faster_whisper import WhisperModel
import os
model = os.getenv("WHISPER_MODEL", "tiny.en")
print(f"Pre-downloading faster-whisper model: {model}")
WhisperModel(model, device="cpu", compute_type="int8")
print("Model downloaded and cached.")
EOF

# Silero VAD is downloaded from torch.hub on first startup (cached in
# ~/.cache/torch/hub). Pre-caching it here keeps cold-start fast.
RUN python - <<'EOF'
import torch, os
print("Pre-downloading Silero VAD model")
torch.hub.load("snakers4/silero-vad", model="silero_vad", force_reload=False, onnx=False)
print("Silero VAD cached.")
EOF

EXPOSE 8000

# Railway injects PORT at runtime; default to 8000 for local docker run.
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
