"""Local LSA (TF-IDF + TruncatedSVD) embedding adapter — no internet required.

This adapter loads the pre-fitted sklearn pipeline produced by
``scripts/generate_sfia_embeddings_migration.py --embedder lsa``.
It embeds query text into the same 384-dim vector space as the
pre-computed embeddings stored in ``framework_skill_levels``.

Prefer ``SentenceTransformersEmbeddingService`` for better retrieval quality
when internet is available to download the model on first use.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from src.domain.ports.embedding_service import IEmbeddingService

DEFAULT_MODEL_PATH = os.path.join(
    os.path.dirname(__file__),
    "..",
    "..",
    "data",
    "sfia_lsa_model.joblib",
)


class SklearnLsaEmbeddingService(IEmbeddingService):
    """Offline embedding adapter backed by a pre-fitted TF-IDF + SVD pipeline.

    The pipeline is loaded from ``model_path`` (joblib format).
    Vectors are L2-normalised so cosine similarity via pgvector ``<=>`` works.
    """

    def __init__(self, model_path: str = DEFAULT_MODEL_PATH) -> None:
        import joblib

        path = Path(model_path).resolve()
        if not path.exists():
            raise FileNotFoundError(
                f"LSA model not found at {path}. "
                "Regenerate it with:\n"
                "  python scripts/generate_sfia_embeddings_migration.py --embedder lsa"
            )
        self._pipeline = joblib.load(str(path))

    async def embed(self, text: str) -> list[float]:
        return await asyncio.to_thread(self._encode, text)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return await asyncio.to_thread(self._encode_batch, texts)

    def _encode(self, text: str) -> list[float]:
        vec = self._pipeline.transform([text])
        return vec[0].tolist()

    def _encode_batch(self, texts: list[str]) -> list[list[float]]:
        vecs = self._pipeline.transform(texts)
        return vecs.tolist()
