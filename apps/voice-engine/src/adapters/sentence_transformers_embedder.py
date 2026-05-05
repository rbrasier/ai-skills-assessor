"""Local embedding adapter using sentence-transformers (no API key required).

Default model: ``all-MiniLM-L6-v2`` (384 dims, ~80 MB).
Downloaded once on first use and cached in ~/.cache/torch/sentence_transformers/.

This is the recommended alternative to ``OpenAIEmbeddingService`` for
environments where no OpenAI API key is available (local dev, CI, self-hosted).
The embedding dimension (384) differs from OpenAI's 1536 — the database schema
must use ``vector(384)`` when this adapter is active.
"""

from __future__ import annotations

import asyncio

from src.domain.ports.embedding_service import IEmbeddingService

DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DIMENSIONS = 384


class SentenceTransformersEmbeddingService(IEmbeddingService):
    """Adapter wrapping sentence-transformers for local CPU/GPU inference.

    ``normalize_embeddings=True`` ensures unit vectors for cosine similarity,
    matching the ``<=>`` (cosine distance) operator used by pgvector queries.
    """

    def __init__(self, model_name: str = DEFAULT_MODEL) -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)

    async def embed(self, text: str) -> list[float]:
        return await asyncio.to_thread(self._encode_one, text)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return await asyncio.to_thread(self._encode_batch, texts)

    def _encode_one(self, text: str) -> list[float]:
        return self._model.encode(text, normalize_embeddings=True).tolist()

    def _encode_batch(self, texts: list[str]) -> list[list[float]]:
        return self._model.encode(texts, normalize_embeddings=True).tolist()
