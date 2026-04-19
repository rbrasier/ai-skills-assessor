"""FastAPI application entry point for the voice engine.

The Phase 1 application only mounts the routers from ``src.api.routes``. Adapter
wiring (Daily, pgvector, Postgres, Anthropic) happens in subsequent phases via
``app.state`` so that handlers can resolve their dependencies cleanly.
"""

from __future__ import annotations

from fastapi import FastAPI

from src.api.routes import router


def create_app() -> FastAPI:
    app = FastAPI(
        title="AI Skills Assessor — Voice Engine",
        version="0.2.0",
        description="Phase 1 scaffold: health + assessment trigger stub.",
    )
    app.include_router(router)
    return app


app = create_app()
