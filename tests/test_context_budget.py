"""
Tests for core.context_budget (F-057 — Global Token Budget / Context Window Manager).

Tests cover:
- Token estimation heuristic
- Text truncation with boundary detection
- ContextLayer enum ordering and membership
- LayerAllocation dataclass
- ContextBudget initialisation (default and custom)
- set_content with auto-truncation
- get_content retrieval
- Budget accounting (used, remaining, over budget)
- Redistribution of unused budget
- Summary output
- Edge cases (unicode, empty, single-char, large text)
"""

from __future__ import annotations

import pytest

from core.context_budget import (
    ContextBudget,
    ContextLayer,
    LayerAllocation,
    estimate_tokens,
    truncate_to_tokens,
)


# ── Token Estimation ──────────────────────────────────────────


class TestEstimateTokens:
    """Tests for the estimate_tokens heuristic."""

    def test_basic_estimate(self):
        """4 characters ≈ 1 token."""
        assert estimate_tokens("abcd") == 1

    def test_empty_string(self):
        assert estimate_tokens("") == 0

    def test_minimum_one_token(self):
        """Even a single character should return at least 1."""
        assert estimate_tokens("a") == 1

    def test_longer_text(self):
        text = "Hello, World! " * 100  # 1400 chars
        tokens = estimate_tokens(text)
        assert tokens == len(text) // 4

    def test_unicode_text(self):
        """Unicode characters are counted by Python len()."""
        text = "日本語テスト" * 10  # 60 chars
        tokens = estimate_tokens(text)
        assert tokens == len(text) // 4


# ── Truncation ────────────────────────────────────────────────


class TestTruncateToTokens:
    """Tests for truncate_to_tokens."""

    def test_within_budget_unchanged(self):
        text = "Short text."
        result = truncate_to_tokens(text, 100)
        assert result == text

    def test_over_budget_truncated(self):
        text = "A" * 1000  # ~250 tokens
        result = truncate_to_tokens(text, 50)  # 50 * 4 = 200 chars budget
        assert len(result) < len(text)
        assert "truncated" in result

    def test_sentence_boundary(self):
        """Should truncate at a sentence boundary when possible."""
        text = "First sentence. Second sentence. Third sentence that is very long " + "x" * 500
        result = truncate_to_tokens(text, 30)  # 120 chars
        assert "truncated" in result
        # Should break at a sentence
        assert "First sentence." in result

    def test_paragraph_boundary(self):
        """Should prefer paragraph boundaries over sentence boundaries."""
        text = "First paragraph.\n\nSecond paragraph that is longer. " + "x" * 500
        result = truncate_to_tokens(text, 30)  # 120 chars
        assert "truncated" in result
        assert "First paragraph." in result

    def test_empty_text(self):
        result = truncate_to_tokens("", 100)
        assert result == ""

    def test_zero_budget(self):
        result = truncate_to_tokens("Some text", 0)
        assert result == ""

    def test_negative_budget(self):
        result = truncate_to_tokens("Some text", -5)
        assert result == ""


# ── Context Layer ─────────────────────────────────────────────


class TestContextLayer:
    """Tests for the ContextLayer enum."""

    def test_all_layers_exist(self):
        assert len(ContextLayer) == 5

    def test_priority_ordering(self):
        """Lower value = higher priority."""
        layers = sorted(ContextLayer)
        assert layers[0] == ContextLayer.SYSTEM_PROMPT
        assert layers[1] == ContextLayer.CONVERSATION_HISTORY
        assert layers[2] == ContextLayer.MEMORIES_BELIEFS
        assert layers[3] == ContextLayer.WORLD_CONTEXT
        assert layers[4] == ContextLayer.LLM_INJECTIONS

    def test_integer_values(self):
        assert ContextLayer.SYSTEM_PROMPT == 0
        assert ContextLayer.LLM_INJECTIONS == 4

    def test_name_access(self):
        assert ContextLayer.SYSTEM_PROMPT.name == "SYSTEM_PROMPT"
        assert ContextLayer.WORLD_CONTEXT.name == "WORLD_CONTEXT"


# ── Layer Allocation ──────────────────────────────────────────


class TestLayerAllocation:
    """Tests for the LayerAllocation dataclass."""

    def test_fields(self):
        alloc = LayerAllocation(
            layer=ContextLayer.SYSTEM_PROMPT,
            max_tokens=5000,
            content="test",
            token_count=1,
            truncated=False,
        )
        assert alloc.layer == ContextLayer.SYSTEM_PROMPT
        assert alloc.max_tokens == 5000
        assert alloc.content == "test"
        assert alloc.token_count == 1
        assert alloc.truncated is False

    def test_frozen(self):
        alloc = LayerAllocation(
            layer=ContextLayer.SYSTEM_PROMPT,
            max_tokens=5000,
        )
        with pytest.raises(AttributeError):
            alloc.content = "changed"  # type: ignore[misc]

    def test_to_dict(self):
        alloc = LayerAllocation(
            layer=ContextLayer.MEMORIES_BELIEFS,
            max_tokens=1000,
            content="stuff",
            token_count=100,
            truncated=True,
        )
        d = alloc.to_dict()
        assert d["layer"] == "MEMORIES_BELIEFS"
        assert d["max_tokens"] == 1000
        assert d["token_count"] == 100
        assert d["truncated"] is True
        assert d["utilization_pct"] == 10.0

    def test_to_dict_zero_max(self):
        """Zero max_tokens should not cause division by zero."""
        alloc = LayerAllocation(
            layer=ContextLayer.LLM_INJECTIONS,
            max_tokens=0,
        )
        d = alloc.to_dict()
        assert d["utilization_pct"] == 0.0

    def test_defaults(self):
        alloc = LayerAllocation(
            layer=ContextLayer.WORLD_CONTEXT,
            max_tokens=100,
        )
        assert alloc.content == ""
        assert alloc.token_count == 0
        assert alloc.truncated is False


# ── Context Budget Init ───────────────────────────────────────


class TestContextBudgetInit:
    """Tests for ContextBudget initialisation."""

    def test_default_target(self):
        budget = ContextBudget()
        assert budget.target_tokens == 32768

    def test_custom_target(self):
        budget = ContextBudget(target_tokens=8192)
        assert budget.target_tokens == 8192

    def test_zero_target_raises(self):
        with pytest.raises(ValueError, match="positive"):
            ContextBudget(target_tokens=0)

    def test_negative_target_raises(self):
        with pytest.raises(ValueError, match="positive"):
            ContextBudget(target_tokens=-100)

    def test_all_layers_initialized(self):
        budget = ContextBudget()
        for layer in ContextLayer:
            alloc = budget.get_allocation(layer)
            assert alloc.max_tokens > 0
            assert alloc.content == ""
            assert alloc.token_count == 0

    def test_custom_allocations(self):
        custom = {
            ContextLayer.SYSTEM_PROMPT: 0.50,
            ContextLayer.CONVERSATION_HISTORY: 0.50,
            ContextLayer.MEMORIES_BELIEFS: 0.0,
            ContextLayer.WORLD_CONTEXT: 0.0,
            ContextLayer.LLM_INJECTIONS: 0.0,
        }
        budget = ContextBudget(target_tokens=10000, allocations=custom)
        assert budget.get_allocation(ContextLayer.SYSTEM_PROMPT).max_tokens == 5000
        assert budget.get_allocation(ContextLayer.CONVERSATION_HISTORY).max_tokens == 5000

    def test_layers_property(self):
        budget = ContextBudget()
        assert budget.layers == sorted(ContextLayer)

    def test_repr(self):
        budget = ContextBudget(target_tokens=1000)
        r = repr(budget)
        assert "1000" in r
        assert "used=0" in r


# ── Set Content ───────────────────────────────────────────────


class TestSetContent:
    """Tests for setting content on layers."""

    def test_within_budget(self):
        budget = ContextBudget(target_tokens=10000)
        alloc = budget.set_content(
            ContextLayer.SYSTEM_PROMPT,
            "Short prompt.",
        )
        assert alloc.truncated is False
        assert alloc.content == "Short prompt."
        assert alloc.token_count > 0

    def test_truncation(self):
        budget = ContextBudget(target_tokens=100)
        # 100 * 0.15 = 15 tokens = ~60 chars for system prompt
        long_text = "A" * 500
        alloc = budget.set_content(
            ContextLayer.SYSTEM_PROMPT,
            long_text,
        )
        assert alloc.truncated is True
        assert len(alloc.content) < len(long_text)
        assert "truncated" in alloc.content

    def test_multiple_layers(self):
        budget = ContextBudget(target_tokens=10000)
        budget.set_content(ContextLayer.SYSTEM_PROMPT, "System prompt text")
        budget.set_content(ContextLayer.CONVERSATION_HISTORY, "History text")
        budget.set_content(ContextLayer.WORLD_CONTEXT, "World info")

        assert budget.get_content(ContextLayer.SYSTEM_PROMPT) == "System prompt text"
        assert budget.get_content(ContextLayer.CONVERSATION_HISTORY) == "History text"
        assert budget.get_content(ContextLayer.WORLD_CONTEXT) == "World info"

    def test_empty_content(self):
        budget = ContextBudget(target_tokens=10000)
        alloc = budget.set_content(ContextLayer.SYSTEM_PROMPT, "")
        assert alloc.content == ""
        assert alloc.token_count == 0
        assert alloc.truncated is False

    def test_overwrite_content(self):
        budget = ContextBudget(target_tokens=10000)
        budget.set_content(ContextLayer.SYSTEM_PROMPT, "first")
        alloc = budget.set_content(ContextLayer.SYSTEM_PROMPT, "second")
        assert alloc.content == "second"


# ── Get Content ───────────────────────────────────────────────


class TestGetContent:
    """Tests for getting content from layers."""

    def test_existing_content(self):
        budget = ContextBudget(target_tokens=10000)
        budget.set_content(ContextLayer.WORLD_CONTEXT, "World data")
        assert budget.get_content(ContextLayer.WORLD_CONTEXT) == "World data"

    def test_empty_layer(self):
        budget = ContextBudget(target_tokens=10000)
        assert budget.get_content(ContextLayer.LLM_INJECTIONS) == ""

    def test_after_truncation(self):
        budget = ContextBudget(target_tokens=100)
        long_text = "X" * 500
        budget.set_content(ContextLayer.SYSTEM_PROMPT, long_text)
        content = budget.get_content(ContextLayer.SYSTEM_PROMPT)
        assert "truncated" in content
        assert len(content) < len(long_text)


# ── Budget Accounting ─────────────────────────────────────────


class TestBudgetAccounting:
    """Tests for budget accounting methods."""

    def test_total_used_empty(self):
        budget = ContextBudget(target_tokens=10000)
        assert budget.total_used() == 0

    def test_total_used_with_content(self):
        budget = ContextBudget(target_tokens=10000)
        text = "Hello world test"  # 16 chars = 4 tokens
        budget.set_content(ContextLayer.SYSTEM_PROMPT, text)
        assert budget.total_used() == estimate_tokens(text)

    def test_total_remaining(self):
        budget = ContextBudget(target_tokens=10000)
        assert budget.total_remaining() == 10000
        budget.set_content(ContextLayer.SYSTEM_PROMPT, "Hello world test")
        assert budget.total_remaining() == 10000 - estimate_tokens("Hello world test")

    def test_remaining_tokens_per_layer(self):
        budget = ContextBudget(target_tokens=10000)
        limit = budget.get_allocation(ContextLayer.SYSTEM_PROMPT).max_tokens
        budget.set_content(ContextLayer.SYSTEM_PROMPT, "Hi")
        remaining = budget.remaining_tokens(ContextLayer.SYSTEM_PROMPT)
        assert remaining == limit - estimate_tokens("Hi")

    def test_is_over_budget_false(self):
        budget = ContextBudget(target_tokens=10000)
        assert budget.is_over_budget() is False

    def test_is_over_budget_not_possible_with_truncation(self):
        """With truncation, individual layers can't exceed their limit."""
        budget = ContextBudget(target_tokens=100)
        for layer in ContextLayer:
            budget.set_content(layer, "x" * 10000)
        # Each layer is truncated to its limit, so total should not
        # exceed target (each layer gets <= its % of target)
        assert budget.total_used() <= budget.target_tokens


# ── Summary ───────────────────────────────────────────────────


class TestSummary:
    """Tests for the summary method."""

    def test_summary_structure(self):
        budget = ContextBudget(target_tokens=10000)
        s = budget.summary()
        assert "target_tokens" in s
        assert "total_used" in s
        assert "total_remaining" in s
        assert "is_over_budget" in s
        assert "layers" in s

    def test_summary_layers(self):
        budget = ContextBudget(target_tokens=10000)
        s = budget.summary()
        assert "SYSTEM_PROMPT" in s["layers"]
        assert "CONVERSATION_HISTORY" in s["layers"]
        assert "MEMORIES_BELIEFS" in s["layers"]
        assert "WORLD_CONTEXT" in s["layers"]
        assert "LLM_INJECTIONS" in s["layers"]

    def test_summary_values(self):
        budget = ContextBudget(target_tokens=10000)
        budget.set_content(ContextLayer.SYSTEM_PROMPT, "Test prompt")
        s = budget.summary()
        assert s["total_used"] > 0
        assert s["total_remaining"] < 10000

    def test_summary_with_truncation(self):
        budget = ContextBudget(target_tokens=100)
        budget.set_content(ContextLayer.SYSTEM_PROMPT, "A" * 500)
        s = budget.summary()
        assert s["layers"]["SYSTEM_PROMPT"]["truncated"] is True


# ── Redistribute Unused ───────────────────────────────────────


class TestRedistributeUnused:
    """Tests for unused budget redistribution."""

    def test_basic_redistribution(self):
        budget = ContextBudget(target_tokens=10000)
        # System prompt uses almost nothing
        budget.set_content(ContextLayer.SYSTEM_PROMPT, "Hi")
        # World context was truncated
        long_world = "W" * 50000
        budget.set_content(ContextLayer.WORLD_CONTEXT, long_world)

        old_world_limit = budget.get_allocation(ContextLayer.WORLD_CONTEXT).max_tokens
        budget.redistribute_unused()
        new_world_limit = budget.get_allocation(ContextLayer.WORLD_CONTEXT).max_tokens
        # Should have more room now
        assert new_world_limit > old_world_limit

    def test_no_truncated_layers(self):
        """When nothing was truncated, redistribution is a no-op."""
        budget = ContextBudget(target_tokens=100000)
        budget.set_content(ContextLayer.SYSTEM_PROMPT, "Short")
        budget.set_content(ContextLayer.CONVERSATION_HISTORY, "Also short")

        old_limit = budget.get_allocation(ContextLayer.SYSTEM_PROMPT).max_tokens
        budget.redistribute_unused()
        new_limit = budget.get_allocation(ContextLayer.SYSTEM_PROMPT).max_tokens
        assert new_limit == old_limit

    def test_all_layers_empty(self):
        """When all layers are empty, redistribution is a no-op."""
        budget = ContextBudget(target_tokens=10000)
        budget.redistribute_unused()
        # Should not crash, limits unchanged
        for layer in ContextLayer:
            assert budget.get_allocation(layer).max_tokens > 0


# ── Edge Cases ────────────────────────────────────────────────


class TestEdgeCases:
    """Edge case tests."""

    def test_unicode_content(self):
        budget = ContextBudget(target_tokens=10000)
        text = "日本語のテスト 🎮 emoji content"
        alloc = budget.set_content(ContextLayer.WORLD_CONTEXT, text)
        assert alloc.content == text
        assert alloc.token_count > 0

    def test_single_char(self):
        budget = ContextBudget(target_tokens=10000)
        alloc = budget.set_content(ContextLayer.LLM_INJECTIONS, "x")
        assert alloc.token_count == 1
        assert alloc.truncated is False

    def test_very_small_budget(self):
        budget = ContextBudget(target_tokens=10)
        # Each layer gets a tiny allocation
        budget.set_content(ContextLayer.SYSTEM_PROMPT, "A" * 100)
        alloc = budget.get_allocation(ContextLayer.SYSTEM_PROMPT)
        assert alloc.truncated is True

    def test_large_budget(self):
        budget = ContextBudget(target_tokens=128000)
        text = "Content " * 1000  # ~8000 chars = ~2000 tokens
        alloc = budget.set_content(ContextLayer.SYSTEM_PROMPT, text)
        # 128000 * 0.15 = 19200 tokens — plenty of room
        assert alloc.truncated is False

    def test_newlines_in_content(self):
        budget = ContextBudget(target_tokens=10000)
        text = "Line 1\nLine 2\n\nParagraph 2\nLine 3"
        alloc = budget.set_content(ContextLayer.MEMORIES_BELIEFS, text)
        assert alloc.content == text
        assert "\n" in alloc.content
