"""
Jericho — Embedding Provider

Provides semantic text embeddings via sentence-transformers for
relevance scoring in the memory influence system.  The model loads
lazily on first use and is shared across all callers (singleton).

When sentence-transformers is not installed, all methods degrade
gracefully — ``is_available`` returns False and scoring falls back
to keyword-based Jaccard similarity in the calling code.
"""

from __future__ import annotations

import logging
from typing import Any

from config.settings import EMBEDDING_MODEL_NAME

log = logging.getLogger(__name__)

# ─── Singleton ────────────────────────────────────────────────

_provider_instance: EmbeddingProvider | None = None


def get_embedding_provider() -> EmbeddingProvider:
    """Return the shared EmbeddingProvider singleton."""
    global _provider_instance
    if _provider_instance is None:
        _provider_instance = EmbeddingProvider()
    return _provider_instance


def reset_embedding_provider() -> None:
    """Reset the singleton (for testing)."""
    global _provider_instance
    _provider_instance = None


# ─── Provider ─────────────────────────────────────────────────


class EmbeddingProvider:
    """
    Lazy-loading semantic embedding provider.

    Usage::

        from core.embeddings import get_embedding_provider

        provider = get_embedding_provider()
        if provider.is_available:
            score = provider.similarity("AI ethics", "moral responsibility")
    """

    def __init__(self, model_name: str | None = None) -> None:
        self._model_name = model_name or EMBEDDING_MODEL_NAME
        self._model: Any = None
        self._available: bool | None = None  # None = not yet attempted

    # ── Properties ────────────────────────────────────────────

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def is_available(self) -> bool:
        """Whether the embedding model loaded successfully."""
        if self._available is None:
            self._load_model()
        return self._available  # type: ignore[return-value]

    # ── Core Methods ──────────────────────────────────────────

    def encode(self, text: str) -> Any:
        """
        Encode a text string into an embedding vector.

        Returns a numpy array, or None if the model is unavailable.
        """
        if not self.is_available:
            return None
        try:
            return self._model.encode(text, convert_to_numpy=True)
        except Exception as exc:
            log.warning("Embedding encode failed: %s", exc)
            return None

    def similarity(self, text_a: str, text_b: str) -> float:
        """
        Compute cosine similarity between two text strings.

        Returns 0.0 if the model is unavailable or encoding fails.
        """
        if not self.is_available:
            return 0.0
        try:
            embeddings = self._model.encode(
                [text_a, text_b], convert_to_numpy=True,
            )
            return float(self._cosine_similarity(embeddings[0], embeddings[1]))
        except Exception as exc:
            log.warning("Embedding similarity failed: %s", exc)
            return 0.0

    def batch_similarity(
        self, query: str, candidates: list[str],
    ) -> list[float]:
        """
        Compute cosine similarity of *query* against each candidate.

        Returns a list of floats (same length as *candidates*).
        Returns all zeros if the model is unavailable.
        """
        if not candidates:
            return []
        if not self.is_available:
            return [0.0] * len(candidates)
        try:
            all_texts = [query] + candidates
            embeddings = self._model.encode(all_texts, convert_to_numpy=True)
            query_emb = embeddings[0]
            return [
                float(self._cosine_similarity(query_emb, embeddings[i + 1]))
                for i in range(len(candidates))
            ]
        except Exception as exc:
            log.warning("Embedding batch_similarity failed: %s", exc)
            return [0.0] * len(candidates)

    # ── Internal ──────────────────────────────────────────────

    def _load_model(self) -> None:
        """Attempt to load the sentence-transformers model."""
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self._model_name)
            self._available = True
            log.info(
                "Loaded embedding model: %s", self._model_name,
            )
        except ImportError:
            self._available = False
            log.info(
                "sentence-transformers not installed — "
                "falling back to Jaccard scoring",
            )
        except Exception as exc:
            self._available = False
            log.warning(
                "Failed to load embedding model '%s': %s",
                self._model_name, exc,
            )

    @staticmethod
    def _cosine_similarity(vec_a: Any, vec_b: Any) -> float:
        """Cosine similarity between two numpy vectors."""
        import numpy as np

        dot = np.dot(vec_a, vec_b)
        norm_a = np.linalg.norm(vec_a)
        norm_b = np.linalg.norm(vec_b)
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return float(dot / (norm_a * norm_b))

    def __repr__(self) -> str:
        status = (
            "available" if self._available
            else "unavailable" if self._available is False
            else "not loaded"
        )
        return f"EmbeddingProvider(model='{self._model_name}', status={status})"
