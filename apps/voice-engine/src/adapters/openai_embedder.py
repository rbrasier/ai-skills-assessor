"""OpenAI embedding adapter — ``text-embedding-3-small`` (1536 dims)."""

from __future__ import annotations

from src.domain.ports.embedding_service import IEmbeddingService


class OpenAIEmbeddingService(IEmbeddingService):
    """Adapter for OpenAI embedding API using ``text-embedding-3-small``."""

    def __init__(self, api_key: str, model: str = "text-embedding-3-small") -> None:
        # Lazy import so the lean CI image (no openai installed) still loads.
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model

    async def embed(self, text: str) -> list[float]:
        response = await self._client.embeddings.create(
            input=text,
            model=self._model,
        )
        return response.data[0].embedding

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts. OpenAI accepts up to 2048 inputs per call."""
        response = await self._client.embeddings.create(
            input=texts,
            model=self._model,
        )
        return [item.embedding for item in response.data]
