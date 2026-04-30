"""``IEmbeddingService`` port — text embedding for RAG ingestion and retrieval."""

from __future__ import annotations

from abc import ABC, abstractmethod


class IEmbeddingService(ABC):
    """Port for embedding text into vectors for RAG retrieval."""

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        """Embed a single text string."""
        ...

    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts in one API call."""
        ...
