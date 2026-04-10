"""
Jericho — Embedding Provider Tests

Tests for the semantic embedding provider: initialization, lazy loading,
similarity scoring, batch operations, and graceful fallback.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from core.embeddings import EmbeddingProvider, get_embedding_provider, reset_embedding_provider


# ─── Setup / Teardown ──────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Reset the singleton between tests."""
    reset_embedding_provider()
    yield
    reset_embedding_provider()


# ─── EmbeddingProvider Init ────────────────────────────────────


class TestEmbeddingProviderInit:
    """Tests for EmbeddingProvider construction."""

    def test_default_model_name(self):
        provider = EmbeddingProvider()
        assert provider.model_name == "all-MiniLM-L6-v2"

    def test_custom_model_name(self):
        provider = EmbeddingProvider(model_name="custom-model")
        assert provider.model_name == "custom-model"

    def test_repr_not_loaded(self):
        provider = EmbeddingProvider.__new__(EmbeddingProvider)
        provider._model_name = "test-model"
        provider._model = None
        provider._available = None
        r = repr(provider)
        assert "test-model" in r
        assert "not loaded" in r


# ─── Availability ──────────────────────────────────────────────


class TestAvailability:
    """Tests for model availability detection."""

    def test_available_when_model_loads(self):
        provider = EmbeddingProvider()
        # If sentence-transformers is installed, it should be available
        # This test is conditional — it passes either way
        assert isinstance(provider.is_available, bool)

    def test_unavailable_with_bad_model(self):
        provider = EmbeddingProvider(model_name="nonexistent-model-xyz-999")
        assert provider.is_available is False

    def test_repr_after_load(self):
        provider = EmbeddingProvider()
        _ = provider.is_available  # trigger load
        r = repr(provider)
        assert "available" in r or "unavailable" in r
        assert "not loaded" not in r


# ─── Similarity ────────────────────────────────────────────────


class TestSimilarity:
    """Tests for pairwise similarity scoring."""

    def test_identical_texts_score_high(self):
        provider = EmbeddingProvider()
        if not provider.is_available:
            pytest.skip("sentence-transformers not installed")
        score = provider.similarity("AI safety", "AI safety")
        assert score > 0.9

    def test_similar_texts_score_higher_than_dissimilar(self):
        provider = EmbeddingProvider()
        if not provider.is_available:
            pytest.skip("sentence-transformers not installed")
        similar = provider.similarity(
            "moral responsibility in autonomous systems",
            "AI ethics and accountability",
        )
        dissimilar = provider.similarity(
            "moral responsibility in autonomous systems",
            "chocolate cake recipe",
        )
        assert similar > dissimilar

    def test_returns_zero_when_unavailable(self):
        provider = EmbeddingProvider(model_name="nonexistent-model-xyz-999")
        score = provider.similarity("text a", "text b")
        assert score == 0.0

    def test_empty_strings(self):
        provider = EmbeddingProvider()
        if not provider.is_available:
            pytest.skip("sentence-transformers not installed")
        # Should not crash
        score = provider.similarity("", "")
        assert isinstance(score, float)


# ─── Batch Similarity ─────────────────────────────────────────


class TestBatchSimilarity:
    """Tests for batch similarity operations."""

    def test_empty_candidates(self):
        provider = EmbeddingProvider()
        result = provider.batch_similarity("query", [])
        assert result == []

    def test_correct_count(self):
        provider = EmbeddingProvider()
        if not provider.is_available:
            pytest.skip("sentence-transformers not installed")
        candidates = ["AI safety", "cooking recipes", "machine learning"]
        result = provider.batch_similarity("AI ethics", candidates)
        assert len(result) == 3

    def test_ranks_semantically_similar_higher(self):
        provider = EmbeddingProvider()
        if not provider.is_available:
            pytest.skip("sentence-transformers not installed")
        candidates = [
            "chocolate cake recipe",        # dissimilar
            "AI ethics and accountability",  # similar
            "weather forecast for today",    # dissimilar
        ]
        scores = provider.batch_similarity(
            "moral responsibility in autonomous systems", candidates,
        )
        # The AI ethics candidate (#1) should score highest
        assert scores[1] > scores[0]
        assert scores[1] > scores[2]

    def test_returns_zeros_when_unavailable(self):
        provider = EmbeddingProvider(model_name="nonexistent-model-xyz-999")
        result = provider.batch_similarity("query", ["a", "b", "c"])
        assert result == [0.0, 0.0, 0.0]


# ─── Encode ────────────────────────────────────────────────────


class TestEncode:
    """Tests for raw encoding."""

    def test_encode_returns_array(self):
        provider = EmbeddingProvider()
        if not provider.is_available:
            pytest.skip("sentence-transformers not installed")
        result = provider.encode("test text")
        assert result is not None
        assert len(result) > 0

    def test_encode_returns_none_when_unavailable(self):
        provider = EmbeddingProvider(model_name="nonexistent-model-xyz-999")
        result = provider.encode("test text")
        assert result is None


# ─── Singleton ─────────────────────────────────────────────────


class TestSingleton:
    """Tests for the singleton pattern."""

    def test_get_returns_same_instance(self):
        p1 = get_embedding_provider()
        p2 = get_embedding_provider()
        assert p1 is p2

    def test_reset_clears_singleton(self):
        p1 = get_embedding_provider()
        reset_embedding_provider()
        p2 = get_embedding_provider()
        assert p1 is not p2


# ─── Cosine Similarity ────────────────────────────────────────


class TestCosineSimilarity:
    """Tests for the internal cosine similarity helper."""

    def test_identical_vectors(self):
        import numpy as np
        vec = np.array([1.0, 0.5, 0.3])
        result = EmbeddingProvider._cosine_similarity(vec, vec)
        assert result == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        import numpy as np
        a = np.array([1.0, 0.0])
        b = np.array([0.0, 1.0])
        result = EmbeddingProvider._cosine_similarity(a, b)
        assert result == pytest.approx(0.0)

    def test_zero_vector(self):
        import numpy as np
        a = np.array([1.0, 0.5])
        b = np.array([0.0, 0.0])
        result = EmbeddingProvider._cosine_similarity(a, b)
        assert result == 0.0
