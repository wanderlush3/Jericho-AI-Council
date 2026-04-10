"""
Tests for core.api_client — Unified API Client (F-002)

All network calls are mocked. No real API requests are made.
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from core.api_client import (
    APIAuthenticationError,
    APIClient,
    APIConnectionError,
    APIError,
    APIRateLimitError,
    ChatMessage,
    ChatResponse,
)
from core.registry import CouncilMember


# ─── Fixtures ──────────────────────────────────────────────────


def _make_member(**overrides) -> CouncilMember:
    """Create a CouncilMember for testing."""
    defaults = {
        "name": "TestAgent",
        "role": "Tester",
        "description": "A test council member",
        "api_provider": "openrouter",
        "model": "anthropic/claude-3.5-sonnet",
        "system_prompt": "You are a test agent.",
        "vote_weight": 1.0,
    }
    defaults.update(overrides)
    return CouncilMember(**defaults)


def _make_success_response(
    content: str = "Hello from the API",
    model: str = "anthropic/claude-3.5-sonnet",
) -> dict:
    """Create a valid OpenAI-style chat completion response."""
    return {
        "id": "chatcmpl-test123",
        "object": "chat.completion",
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 50,
            "completion_tokens": 20,
            "total_tokens": 70,
        },
    }


def _mock_httpx_response(
    status_code: int = 200,
    json_data: dict | None = None,
    text: str = "",
) -> httpx.Response:
    """Create a mock httpx.Response."""
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.text = text or (str(json_data) if json_data else "")
    response.json.return_value = json_data or {}
    return response


@pytest.fixture
def openrouter_member() -> CouncilMember:
    return _make_member(name="Sage", api_provider="openrouter")


@pytest.fixture
def mancer_member() -> CouncilMember:
    return _make_member(
        name="Drift",
        api_provider="mancer",
        model="nothingiisreal/MN-12B-Celeste-V1.9",
    )


@pytest.fixture
def client() -> APIClient:
    """API client with test keys, minimal retry delays."""
    return APIClient(
        openrouter_api_key="test-openrouter-key",
        mancer_api_key="test-mancer-key",
        lmstudio_api_key="test-lmstudio-key",
        max_retries=2,
        retry_delay=0.01,
        timeout=5.0,
        rate_limit_gap=0.0,  # Disable rate limiting in tests
    )


@pytest.fixture
def messages() -> list[ChatMessage]:
    return [ChatMessage(role="user", content="Hello, how are you?")]


# ─── ChatMessage Tests ─────────────────────────────────────────


class TestChatMessage:
    """Tests for the ChatMessage data class."""

    def test_fields(self) -> None:
        msg = ChatMessage(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"

    def test_to_dict(self) -> None:
        msg = ChatMessage(role="assistant", content="Hi there")
        assert msg.to_dict() == {"role": "assistant", "content": "Hi there"}

    def test_frozen(self) -> None:
        msg = ChatMessage(role="user", content="Hello")
        with pytest.raises(AttributeError):
            msg.content = "Modified"  # type: ignore[misc]


# ─── ChatResponse Tests ───────────────────────────────────────


class TestChatResponse:
    """Tests for the ChatResponse data class."""

    def test_fields(self) -> None:
        resp = ChatResponse(
            content="Reply",
            model="test-model",
            provider="openrouter",
            usage={"total_tokens": 100},
            raw={"id": "123"},
        )
        assert resp.content == "Reply"
        assert resp.model == "test-model"
        assert resp.provider == "openrouter"
        assert resp.usage == {"total_tokens": 100}

    def test_defaults(self) -> None:
        resp = ChatResponse(content="Reply", model="m", provider="p")
        assert resp.usage is None
        assert resp.raw == {}

    def test_frozen(self) -> None:
        resp = ChatResponse(content="Reply", model="m", provider="p")
        with pytest.raises(AttributeError):
            resp.content = "Modified"  # type: ignore[misc]


# ─── APIClient Init Tests ─────────────────────────────────────


class TestAPIClientInit:
    """Tests for APIClient initialization and lifecycle."""

    def test_explicit_keys(self) -> None:
        c = APIClient(openrouter_api_key="or-key", mancer_api_key="mn-key")
        assert c._openrouter_key == "or-key"
        assert c._mancer_key == "mn-key"

    def test_keys_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("JERICHO_OPENROUTER_API_KEY", "env-or")
        monkeypatch.setenv("JERICHO_MANCER_API_KEY", "env-mn")
        c = APIClient()
        assert c._openrouter_key == "env-or"
        assert c._mancer_key == "env-mn"

    def test_custom_retries_and_timeout(self) -> None:
        c = APIClient(
            openrouter_api_key="k",
            max_retries=5,
            retry_delay=1.0,
            timeout=30.0,
        )
        assert c._max_retries == 5
        assert c._retry_delay == 1.0
        assert c._timeout == 30.0

    @pytest.mark.asyncio
    async def test_context_manager(self) -> None:
        async with APIClient(openrouter_api_key="k", mancer_api_key="k") as c:
            assert c._http is not None
            assert not c._http.is_closed
        assert c._http is None

    @pytest.mark.asyncio
    async def test_close_idempotent(self) -> None:
        c = APIClient(openrouter_api_key="k")
        await c.close()  # No-op when no client exists
        await c._ensure_client()
        await c.close()
        await c.close()  # Second close is safe


# ─── Endpoint Resolution Tests ────────────────────────────────


class TestEndpointResolution:
    """Tests for _resolve_endpoint."""

    def test_openrouter_url_and_headers(
        self, client: APIClient, openrouter_member: CouncilMember
    ) -> None:
        url, headers = client._resolve_endpoint(openrouter_member)
        assert "/chat/completions" in url
        assert "openrouter.ai" in url
        assert headers["Authorization"] == "Bearer test-openrouter-key"
        assert "HTTP-Referer" in headers
        assert "X-Title" in headers

    def test_mancer_url_and_headers(
        self, client: APIClient, mancer_member: CouncilMember
    ) -> None:
        url, headers = client._resolve_endpoint(mancer_member)
        assert "/chat/completions" in url
        assert "mancer.tech" in url
        assert headers["Authorization"] == "Bearer test-mancer-key"
        assert "HTTP-Referer" not in headers  # Mancer doesn't need these

    def test_unknown_provider_raises(self, client: APIClient) -> None:
        member = _make_member(api_provider="unknown_llm")
        with pytest.raises(ValueError, match="Unknown API provider"):
            client._resolve_endpoint(member)

    def test_lmstudio_url_and_headers(
        self, client: APIClient,
    ) -> None:
        member = _make_member(
            name="Local", api_provider="lmstudio", model="Loaded Model",
        )
        url, headers = client._resolve_endpoint(member)
        assert "/chat/completions" in url
        assert "localhost:1234" in url
        assert headers["Authorization"] == "Bearer test-lmstudio-key"

    def test_lmstudio_no_key_still_works(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """LM Studio should work without an API key (local server)."""
        monkeypatch.delenv("JERICHO_LMSTUDIO_API_KEY", raising=False)
        c = APIClient(
            openrouter_api_key="k", mancer_api_key="k", lmstudio_api_key="",
        )
        member = _make_member(
            name="Local", api_provider="lmstudio", model="Loaded Model",
        )
        url, headers = c._resolve_endpoint(member)
        assert "/chat/completions" in url
        assert "Authorization" not in headers

    def test_lmstudio_custom_base_url(
        self, client: APIClient, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """LM Studio base URL can be overridden via env var."""
        monkeypatch.setenv("JERICHO_LMSTUDIO_BASE_URL", "http://192.168.1.100:9999/v1")
        member = _make_member(
            name="Remote", api_provider="lmstudio", model="Loaded Model",
        )
        url, headers = client._resolve_endpoint(member)
        assert "192.168.1.100:9999" in url
        assert "/chat/completions" in url

    def test_missing_openrouter_key_raises(
        self, openrouter_member: CouncilMember, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("JERICHO_OPENROUTER_API_KEY", raising=False)
        c = APIClient(openrouter_api_key="", mancer_api_key="k")
        with pytest.raises(APIAuthenticationError, match="OpenRouter API key not set"):
            c._resolve_endpoint(openrouter_member)

    def test_missing_mancer_key_raises(
        self, mancer_member: CouncilMember, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("JERICHO_MANCER_API_KEY", raising=False)
        c = APIClient(openrouter_api_key="k", mancer_api_key="")
        with pytest.raises(APIAuthenticationError, match="Mancer API key not set"):
            c._resolve_endpoint(mancer_member)


# ─── Request Building Tests ───────────────────────────────────


class TestRequestBuilding:
    """Tests for _build_request_body."""

    def test_basic_body_shape(
        self, openrouter_member: CouncilMember, messages: list[ChatMessage],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Clear any model override env vars so the member's own model is used
        monkeypatch.delenv("JERICHO_OPENROUTER_MODEL", raising=False)
        monkeypatch.delenv("JERICHO_MANCER_MODEL", raising=False)
        body = APIClient._build_request_body(
            openrouter_member, messages, temperature=0.7, max_tokens=2048
        )
        assert body["model"] == "anthropic/claude-3.5-sonnet"
        assert body["temperature"] == 0.7
        assert body["max_tokens"] == 2048
        assert isinstance(body["messages"], list)

    def test_system_prompt_prepended(
        self, openrouter_member: CouncilMember, messages: list[ChatMessage]
    ) -> None:
        body = APIClient._build_request_body(
            openrouter_member, messages, temperature=0.7, max_tokens=2048
        )
        assert body["messages"][0]["role"] == "system"
        assert body["messages"][0]["content"] == openrouter_member.system_prompt

    def test_user_messages_follow_system(
        self, openrouter_member: CouncilMember
    ) -> None:
        msgs = [
            ChatMessage(role="user", content="Q1"),
            ChatMessage(role="assistant", content="A1"),
            ChatMessage(role="user", content="Q2"),
        ]
        body = APIClient._build_request_body(
            openrouter_member, msgs, temperature=0.5, max_tokens=1000
        )
        assert len(body["messages"]) == 4  # system + 3 user/assistant
        assert body["messages"][1] == {"role": "user", "content": "Q1"}
        assert body["messages"][2] == {"role": "assistant", "content": "A1"}
        assert body["messages"][3] == {"role": "user", "content": "Q2"}

    def test_empty_messages(self, openrouter_member: CouncilMember) -> None:
        body = APIClient._build_request_body(
            openrouter_member, [], temperature=0.7, max_tokens=2048
        )
        assert len(body["messages"]) == 1  # Just the system prompt


# ─── Model Precedence Tests ──────────────────────────────────


class TestModelPrecedence:
    """Tests for reversed model precedence: member model > env var default."""

    def test_member_model_used_when_specific(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When member has a specific model, it is used regardless of env var."""
        monkeypatch.setenv("JERICHO_OPENROUTER_MODEL", "some/other-model")
        member = _make_member(model="anthropic/claude-3.5-sonnet")
        body = APIClient._build_request_body(
            member, [ChatMessage(role="user", content="Hi")],
            temperature=0.7, max_tokens=100,
        )
        assert body["model"] == "anthropic/claude-3.5-sonnet"

    def test_default_falls_back_to_env_var(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When member model is 'Default', falls back to env var."""
        monkeypatch.setenv("JERICHO_OPENROUTER_MODEL", "google/gemini-pro")
        member = _make_member(model="Default")
        body = APIClient._build_request_body(
            member, [ChatMessage(role="user", content="Hi")],
            temperature=0.7, max_tokens=100,
        )
        assert body["model"] == "google/gemini-pro"

    def test_default_case_insensitive(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """'default' (lowercase) also triggers fallback."""
        monkeypatch.setenv("JERICHO_OPENROUTER_MODEL", "google/gemini-pro")
        member = _make_member(model="default")
        body = APIClient._build_request_body(
            member, [ChatMessage(role="user", content="Hi")],
            temperature=0.7, max_tokens=100,
        )
        assert body["model"] == "google/gemini-pro"

    def test_empty_model_falls_back_to_env_var(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When member model is empty string, falls back to env var."""
        monkeypatch.setenv("JERICHO_OPENROUTER_MODEL", "google/gemini-pro")
        member = _make_member(model="")
        body = APIClient._build_request_body(
            member, [ChatMessage(role="user", content="Hi")],
            temperature=0.7, max_tokens=100,
        )
        assert body["model"] == "google/gemini-pro"

    def test_default_no_env_var_keeps_default(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When model is 'Default' and no env var, keeps 'Default' literally."""
        monkeypatch.delenv("JERICHO_OPENROUTER_MODEL", raising=False)
        member = _make_member(model="Default")
        body = APIClient._build_request_body(
            member, [ChatMessage(role="user", content="Hi")],
            temperature=0.7, max_tokens=100,
        )
        assert body["model"] == "Default"

    def test_mancer_member_model_used_when_specific(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Mancer member with specific model ignores env var."""
        monkeypatch.setenv("JERICHO_MANCER_MODEL", "some-mancer-fallback")
        member = _make_member(
            api_provider="mancer", model="mythomax",
        )
        body = APIClient._build_request_body(
            member, [ChatMessage(role="user", content="Hi")],
            temperature=0.7, max_tokens=100,
        )
        assert body["model"] == "mythomax"

    def test_mancer_default_falls_back_to_env_var(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Mancer member with 'Default' model uses env var."""
        monkeypatch.setenv("JERICHO_MANCER_MODEL", "magnum-72b-v4")
        member = _make_member(
            api_provider="mancer", model="Default",
        )
        body = APIClient._build_request_body(
            member, [ChatMessage(role="user", content="Hi")],
            temperature=0.7, max_tokens=100,
        )
        assert body["model"] == "magnum-72b-v4"

    def test_lmstudio_member_model_used_when_specific(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """LM Studio member with specific model ignores env var."""
        monkeypatch.setenv("JERICHO_LMSTUDIO_MODEL", "some-lmstudio-fallback")
        member = _make_member(
            api_provider="lmstudio", model="Loaded Model",
        )
        body = APIClient._build_request_body(
            member, [ChatMessage(role="user", content="Hi")],
            temperature=0.7, max_tokens=100,
        )
        assert body["model"] == "Loaded Model"

    def test_lmstudio_default_falls_back_to_env_var(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """LM Studio member with 'Default' model uses env var."""
        monkeypatch.setenv("JERICHO_LMSTUDIO_MODEL", "my-local-model")
        member = _make_member(
            api_provider="lmstudio", model="Default",
        )
        body = APIClient._build_request_body(
            member, [ChatMessage(role="user", content="Hi")],
            temperature=0.7, max_tokens=100,
        )
        assert body["model"] == "my-local-model"


# ─── Response Parsing Tests ───────────────────────────────────


class TestResponseParsing:
    """Tests for _parse_response."""

    def test_valid_response(self) -> None:
        raw = _make_success_response(content="Hello!", model="claude-3.5")
        resp = APIClient._parse_response(raw, "openrouter")
        assert resp.content == "Hello!"
        assert resp.model == "claude-3.5"
        assert resp.provider == "openrouter"
        assert resp.usage is not None
        assert resp.usage["total_tokens"] == 70

    def test_empty_choices_raises(self) -> None:
        raw = {"choices": [], "model": "test"}
        with pytest.raises(APIError, match="Empty choices"):
            APIClient._parse_response(raw, "openrouter")

    def test_missing_choices_key_raises(self) -> None:
        raw = {"model": "test"}
        with pytest.raises(APIError, match="Malformed"):
            APIClient._parse_response(raw, "mancer")

    def test_missing_message_content_raises(self) -> None:
        raw = {"choices": [{"message": {}}], "model": "test"}
        with pytest.raises(APIError, match="Malformed"):
            APIClient._parse_response(raw, "openrouter")

    def test_usage_extracted_when_present(self) -> None:
        raw = _make_success_response()
        resp = APIClient._parse_response(raw, "openrouter")
        assert resp.usage is not None
        assert "prompt_tokens" in resp.usage

    def test_usage_none_when_absent(self) -> None:
        raw = _make_success_response()
        del raw["usage"]
        resp = APIClient._parse_response(raw, "openrouter")
        assert resp.usage is None

    def test_raw_response_preserved(self) -> None:
        raw = _make_success_response()
        resp = APIClient._parse_response(raw, "openrouter")
        assert resp.raw == raw
        assert "id" in resp.raw


# ─── Retry Behavior Tests ─────────────────────────────────────


class TestRetryBehavior:
    """Tests for retry and error handling in chat()."""

    @pytest.mark.asyncio
    async def test_success_on_first_try(
        self,
        client: APIClient,
        openrouter_member: CouncilMember,
        messages: list[ChatMessage],
    ) -> None:
        mock_response = _mock_httpx_response(200, _make_success_response())
        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            async with client:
                resp = await client.chat(openrouter_member, messages)
        assert resp.content == "Hello from the API"
        assert mock_post.call_count == 1

    @pytest.mark.asyncio
    async def test_auth_error_not_retried(
        self,
        client: APIClient,
        openrouter_member: CouncilMember,
        messages: list[ChatMessage],
    ) -> None:
        mock_response = _mock_httpx_response(401, text="Unauthorized")
        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            async with client:
                with pytest.raises(APIAuthenticationError):
                    await client.chat(openrouter_member, messages)
        assert mock_post.call_count == 1  # No retry

    @pytest.mark.asyncio
    async def test_403_not_retried(
        self,
        client: APIClient,
        openrouter_member: CouncilMember,
        messages: list[ChatMessage],
    ) -> None:
        mock_response = _mock_httpx_response(403, text="Forbidden")
        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            async with client:
                with pytest.raises(APIAuthenticationError):
                    await client.chat(openrouter_member, messages)
        assert mock_post.call_count == 1

    @pytest.mark.asyncio
    async def test_429_retried_then_succeeds(
        self,
        client: APIClient,
        openrouter_member: CouncilMember,
        messages: list[ChatMessage],
    ) -> None:
        fail = _mock_httpx_response(429, text="Rate limited")
        success = _mock_httpx_response(200, _make_success_response())
        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = [fail, success]
            async with client:
                resp = await client.chat(openrouter_member, messages)
        assert resp.content == "Hello from the API"
        assert mock_post.call_count == 2

    @pytest.mark.asyncio
    async def test_500_retried_then_succeeds(
        self,
        client: APIClient,
        openrouter_member: CouncilMember,
        messages: list[ChatMessage],
    ) -> None:
        fail = _mock_httpx_response(500, text="Internal Server Error")
        success = _mock_httpx_response(200, _make_success_response())
        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = [fail, success]
            async with client:
                resp = await client.chat(openrouter_member, messages)
        assert resp.content == "Hello from the API"
        assert mock_post.call_count == 2

    @pytest.mark.asyncio
    async def test_max_retries_exhausted_raises(
        self,
        client: APIClient,
        openrouter_member: CouncilMember,
        messages: list[ChatMessage],
    ) -> None:
        fail = _mock_httpx_response(500, text="Server Error")
        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = fail
            async with client:
                with pytest.raises(APIConnectionError):
                    await client.chat(openrouter_member, messages)
        assert mock_post.call_count == 3  # initial + 2 retries

    @pytest.mark.asyncio
    async def test_429_max_retries_raises_rate_limit(
        self,
        client: APIClient,
        openrouter_member: CouncilMember,
        messages: list[ChatMessage],
    ) -> None:
        fail = _mock_httpx_response(429, text="Rate limited")
        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = fail
            async with client:
                with pytest.raises(APIRateLimitError):
                    await client.chat(openrouter_member, messages)
        assert mock_post.call_count == 3

    @pytest.mark.asyncio
    async def test_connection_error_retried(
        self,
        client: APIClient,
        openrouter_member: CouncilMember,
        messages: list[ChatMessage],
    ) -> None:
        success = _mock_httpx_response(200, _make_success_response())
        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = [httpx.ConnectError("Connection refused"), success]
            async with client:
                resp = await client.chat(openrouter_member, messages)
        assert resp.content == "Hello from the API"
        assert mock_post.call_count == 2

    @pytest.mark.asyncio
    async def test_timeout_retried(
        self,
        client: APIClient,
        openrouter_member: CouncilMember,
        messages: list[ChatMessage],
    ) -> None:
        success = _mock_httpx_response(200, _make_success_response())
        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = [httpx.TimeoutException("Timed out"), success]
            async with client:
                resp = await client.chat(openrouter_member, messages)
        assert resp.content == "Hello from the API"

    @pytest.mark.asyncio
    async def test_4xx_not_retried(
        self,
        client: APIClient,
        openrouter_member: CouncilMember,
        messages: list[ChatMessage],
    ) -> None:
        """Non-auth client errors (e.g. 422) should fail immediately."""
        fail = _mock_httpx_response(422, text="Unprocessable")
        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = fail
            async with client:
                with pytest.raises(APIError) as exc_info:
                    await client.chat(openrouter_member, messages)
                assert exc_info.value.status_code == 422
        assert mock_post.call_count == 1


# ─── Rate Limiting Tests ──────────────────────────────────────


class TestRateLimiting:
    """Tests for per-provider rate limiting."""

    @pytest.mark.asyncio
    async def test_rate_limit_gap_enforced(self) -> None:
        """Requests to the same provider should respect the gap."""
        c = APIClient(
            openrouter_api_key="k",
            mancer_api_key="k",
            rate_limit_gap=0.1,
            max_retries=0,
            retry_delay=0.01,
        )
        member = _make_member(api_provider="openrouter")
        msgs = [ChatMessage(role="user", content="Hi")]

        success = _mock_httpx_response(200, _make_success_response())
        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = success
            async with c:
                await c.chat(member, msgs)
                t1 = time.monotonic()
                await c.chat(member, msgs)
                t2 = time.monotonic()

        # Second call should have waited at least ~0.1s
        assert (t2 - t1) >= 0.08  # Allow small tolerance

    @pytest.mark.asyncio
    async def test_different_providers_independent(self) -> None:
        """Requests to different providers don't affect each other."""
        c = APIClient(
            openrouter_api_key="k",
            mancer_api_key="k",
            rate_limit_gap=0.2,
            max_retries=0,
            retry_delay=0.01,
        )
        or_member = _make_member(name="A", api_provider="openrouter")
        mn_member = _make_member(
            name="B",
            api_provider="mancer",
            model="nothingiisreal/MN-12B-Celeste-V1.9",
        )
        msgs = [ChatMessage(role="user", content="Hi")]

        success = _mock_httpx_response(200, _make_success_response())
        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = success
            async with c:
                await c.chat(or_member, msgs)
                t1 = time.monotonic()
                await c.chat(mn_member, msgs)
                t2 = time.monotonic()

        # Different provider — should not wait
        assert (t2 - t1) < 0.15

    @pytest.mark.asyncio
    async def test_no_rate_limit_on_first_request(self) -> None:
        """First request should not be delayed."""
        c = APIClient(
            openrouter_api_key="k",
            mancer_api_key="k",
            rate_limit_gap=1.0,
            max_retries=0,
            retry_delay=0.01,
        )
        member = _make_member(api_provider="openrouter")
        msgs = [ChatMessage(role="user", content="Hi")]

        success = _mock_httpx_response(200, _make_success_response())
        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = success
            async with c:
                t1 = time.monotonic()
                await c.chat(member, msgs)
                t2 = time.monotonic()

        # First request should be nearly instant
        assert (t2 - t1) < 0.5


# ─── Exception Tests ──────────────────────────────────────────


class TestExceptions:
    """Tests for custom exception classes."""

    def test_api_error_fields(self) -> None:
        err = APIError(
            "Something went wrong",
            status_code=500,
            response_body="error body",
            provider="openrouter",
        )
        assert err.status_code == 500
        assert err.response_body == "error body"
        assert err.provider == "openrouter"
        assert "Something went wrong" in str(err)

    def test_api_error_defaults(self) -> None:
        err = APIError("Basic error")
        assert err.status_code is None
        assert err.response_body == ""
        assert err.provider == ""

    def test_connection_error_is_api_error(self) -> None:
        err = APIConnectionError("timeout", provider="mancer")
        assert isinstance(err, APIError)
        assert err.provider == "mancer"

    def test_rate_limit_error_is_api_error(self) -> None:
        err = APIRateLimitError("429", status_code=429, provider="openrouter")
        assert isinstance(err, APIError)
        assert err.status_code == 429

    def test_auth_error_is_api_error(self) -> None:
        err = APIAuthenticationError("401", status_code=401, provider="openrouter")
        assert isinstance(err, APIError)
        assert err.status_code == 401
