# voice-engine

Phase 1 scaffold for the AI Skills Assessor voice engine.

## Setup

```bash
cd apps/voice-engine
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"          # lean install (Phase 1)
# pip install -e ".[voice,dev]"  # full install (Phase 2+: Pipecat, Daily, etc.)
```

## Run

```bash
uvicorn src.main:app --reload --port 8000
```

Then check `http://localhost:8000/health`.

## Tests

```bash
pytest
ruff check .
mypy src/
```
