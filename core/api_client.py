"""
Jericho — Unified API Client (F-002)

Async client for OpenRouter and Mancer LLM endpoints.
Both providers expose an OpenAI-compatible /chat/completions API.
"""

from __future__ import annotations

import asyncio
import os
import random
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from config.settings import (
    API_MAX_RETRIES,
    API_RETRY_DELAY_SECONDS,
    API_TIMEOUT_SECONDS,
    LMSTUDIO_API_KEY_ENV,
    LMSTUDIO_BASE_URL_ENV,
    LMSTUDIO_DEFAULT_BASE_URL,
    LMSTUDIO_MODEL_ENV,
    MANCER_API_KEY_ENV,
    MANCER_BASE_URL,
    MANCER_MODEL_ENV,
    OPENROUTER_API_KEY_ENV,
    OPENROUTER_BASE_URL,
    OPENROUTER_MODEL_ENV,
)
from core.registry import CouncilMember


# ─── Exceptions ────────────────────────────────────────────────


class APIError(Exception):
    """Base exception for all API client errors."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        response_body: str = "",
        provider: str = "",
    ) -> None:
        self.status_code = status_code
        self.response_body = response_body
        self.provider = provider
        super().__init__(message)


class APIConnectionError(APIError):
    """Network or timeout failure (may be retryable)."""


class APIRateLimitError(APIError):
    """HTTP 429 — too many requests."""


class APIAuthenticationError(APIError):
    """HTTP 401/403 — invalid or missing API key. Not retryable."""


# ─── Data Models ───────────────────────────────────────────────


@dataclass(frozen=True)
class ChatMessage:
    """A single message in a chat conversation."""

    role: str
    content: str

    def to_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass(frozen=True)
class ChatResponse:
    """Parsed response from a chat completion API."""

    content: str
    model: str
    provider: str
    usage: dict[str, Any] | None = None
    raw: dict[str, Any] = field(default_factory=dict)


# ─── Client ────────────────────────────────────────────────────


class APIClient:
    """
    Unified async client for OpenRouter and Mancer chat completions.

    Usage::

        async with APIClient() as client:
            response = await client.chat(member, messages)
            print(response.content)
    """

    def __init__(
        self,
        *,
        openrouter_api_key: str | None = None,
        mancer_api_key: str | None = None,
        lmstudio_api_key: str | None = None,
        max_retries: int = API_MAX_RETRIES,
        retry_delay: float = API_RETRY_DELAY_SECONDS,
        timeout: float = API_TIMEOUT_SECONDS,
        rate_limit_gap: float = 0.5,
    ) -> None:
        self._openrouter_key = openrouter_api_key or os.environ.get(OPENROUTER_API_KEY_ENV, "")
        self._mancer_key = mancer_api_key or os.environ.get(MANCER_API_KEY_ENV, "")
        self._lmstudio_key = lmstudio_api_key or os.environ.get(LMSTUDIO_API_KEY_ENV, "")
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self._timeout = timeout
        self._rate_limit_gap = rate_limit_gap

        self._http: httpx.AsyncClient | None = None

        # Per-provider timestamp of last request (for rate limiting)
        self._last_request_time: dict[str, float] = {}

    # ── Lifecycle ──────────────────────────────────────────────

    async def _ensure_client(self) -> httpx.AsyncClient:
        """Lazily create the httpx client."""
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(timeout=self._timeout)
        return self._http

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._http is not None and not self._http.is_closed:
            await self._http.aclose()
            self._http = None

    async def __aenter__(self) -> APIClient:
        await self._ensure_client()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    # ── Chat Completion ────────────────────────────────────────

    async def chat(
        self,
        member: CouncilMember,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> ChatResponse:
        """
        Send a chat completion request for a council member.

        The member's system_prompt is automatically prepended as the first
        message. Retries on transient errors (429, 5xx) with exponential
        backoff. Fails immediately on authentication errors (401, 403).

        Args:
            member: The council member to send the request for.
            messages: The conversation messages (user/assistant turns).
            temperature: Sampling temperature (0.0–2.0).
            max_tokens: Maximum tokens in the response.

        Returns:
            A ChatResponse with the assistant's reply.

        Raises:
            APIAuthenticationError: On 401/403 (not retried).
            APIRateLimitError: On 429 after all retries exhausted.
            APIConnectionError: On network/timeout after all retries.
            APIError: On other unexpected failures.
        """
        url, headers = self._resolve_endpoint(member)
        body = self._build_request_body(member, messages, temperature, max_tokens)

        # Rate limiting: respect minimum gap per provider
        await self._respect_rate_limit(member.api_provider)

        last_error: Exception | None = None

        for attempt in range(self._max_retries + 1):
            try:
                client = await self._ensure_client()
                response = await client.post(url, json=body, headers=headers)

                self._last_request_time[member.api_provider] = time.monotonic()

                # Auth errors — fail fast, no retry
                if response.status_code in (401, 403):
                    raise APIAuthenticationError(
                        f"Authentication failed for {member.api_provider}: "
                        f"HTTP {response.status_code}",
                        status_code=response.status_code,
                        response_body=response.text,
                        provider=member.api_provider,
                    )

                # Rate limit — retry with backoff
                if response.status_code == 429:
                    last_error = APIRateLimitError(
                        f"Rate limited by {member.api_provider}: HTTP 429",
                        status_code=429,
                        response_body=response.text,
                        provider=member.api_provider,
                    )
                    if attempt < self._max_retries:
                        await self._backoff(attempt)
                        continue
                    raise last_error

                # Server errors — retry with backoff
                if response.status_code >= 500:
                    last_error = APIConnectionError(
                        f"Server error from {member.api_provider}: "
                        f"HTTP {response.status_code}",
                        status_code=response.status_code,
                        response_body=response.text,
                        provider=member.api_provider,
                    )
                    if attempt < self._max_retries:
                        await self._backoff(attempt)
                        continue
                    raise last_error

                # Other client errors — fail immediately
                if response.status_code >= 400:
                    raise APIError(
                        f"Client error from {member.api_provider}: "
                        f"HTTP {response.status_code}",
                        status_code=response.status_code,
                        response_body=response.text,
                        provider=member.api_provider,
                    )

                # Success
                return self._parse_response(response.json(), member.api_provider)

            except (httpx.ConnectError, httpx.TimeoutException, httpx.ReadTimeout) as exc:
                last_error = APIConnectionError(
                    f"Connection error to {member.api_provider}: {exc}",
                    provider=member.api_provider,
                )
                if attempt < self._max_retries:
                    await self._backoff(attempt)
                    continue
                raise last_error from exc

        # Should not reach here, but just in case
        raise APIConnectionError(  # pragma: no cover
            f"All {self._max_retries + 1} attempts exhausted for {member.api_provider}",
            provider=member.api_provider,
        )

    # ── Endpoint Resolution ────────────────────────────────────

    def _resolve_endpoint(self, member: CouncilMember) -> tuple[str, dict[str, str]]:
        """
        Return (url, headers) for a member's API provider.

        Raises:
            ValueError: If the provider is not recognized.
            APIAuthenticationError: If the API key is not set.
        """
        if member.api_provider == "openrouter":
            if not self._openrouter_key:
                raise APIAuthenticationError(
                    f"OpenRouter API key not set. Set {OPENROUTER_API_KEY_ENV} env var.",
                    provider="openrouter",
                )
            return (
                f"{OPENROUTER_BASE_URL}/chat/completions",
                {
                    "Authorization": f"Bearer {self._openrouter_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://jericho.council",
                    "X-Title": "Jericho AI Council",
                },
            )
        elif member.api_provider == "mancer":
            if not self._mancer_key:
                raise APIAuthenticationError(
                    f"Mancer API key not set. Set {MANCER_API_KEY_ENV} env var.",
                    provider="mancer",
                )
            return (
                f"{MANCER_BASE_URL}/chat/completions",
                {
                    "Authorization": f"Bearer {self._mancer_key}",
                    "Content-Type": "application/json",
                },
            )
        elif member.api_provider == "lmstudio":
            base_url = os.environ.get(LMSTUDIO_BASE_URL_ENV, "").strip()
            if not base_url:
                base_url = LMSTUDIO_DEFAULT_BASE_URL
            headers: dict[str, str] = {
                "Content-Type": "application/json",
            }
            # Auth is optional for LM Studio (local server)
            if self._lmstudio_key:
                headers["Authorization"] = f"Bearer {self._lmstudio_key}"
            return (
                f"{base_url}/chat/completions",
                headers,
            )
        else:
            raise ValueError(
                f"Unknown API provider '{member.api_provider}' for member '{member.name}'"
            )

    # ── Request Building ───────────────────────────────────────

    _MODEL_ENV_OVERRIDES: dict[str, str] = {
        "openrouter": OPENROUTER_MODEL_ENV,
        "mancer": MANCER_MODEL_ENV,
        "lmstudio": LMSTUDIO_MODEL_ENV,
    }

    @staticmethod
    def _build_request_body(
        member: CouncilMember,
        messages: list[ChatMessage],
        temperature: float,
        max_tokens: int,
    ) -> dict[str, Any]:
        """Build an OpenAI-compatible chat completion request body."""
        # Prepend system prompt as the first message
        all_messages: list[dict[str, str]] = [
            {"role": "system", "content": member.system_prompt},
        ]
        all_messages.extend(msg.to_dict() for msg in messages)

        # Council member's model takes priority; fall back to Settings
        # default if the member's model is "Default" (case-insensitive)
        # or empty.
        model = member.model
        if not model or model.strip().lower() == "default":
            env_var = APIClient._MODEL_ENV_OVERRIDES.get(member.api_provider)
            if env_var:
                override = os.environ.get(env_var, "").strip()
                if override:
                    model = override

        return {
            "model": model,
            "messages": all_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

    # ── Response Parsing ───────────────────────────────────────

    @staticmethod
    def _parse_response(raw: dict[str, Any], provider: str) -> ChatResponse:
        """
        Parse an OpenAI-compatible chat completion response.

        Raises:
            APIError: If the response is malformed.
        """
        try:
            choices = raw["choices"]
            if not choices:
                raise APIError(
                    "Empty choices list in API response",
                    provider=provider,
                )
            content = choices[0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise APIError(
                f"Malformed API response from {provider}: {exc}",
                provider=provider,
            ) from exc

        return ChatResponse(
            content=content,
            model=raw.get("model", ""),
            provider=provider,
            usage=raw.get("usage"),
            raw=raw,
        )

    # ── Rate Limiting ──────────────────────────────────────────

    async def _respect_rate_limit(self, provider: str) -> None:
        """Wait if needed to respect per-provider rate limit gap."""
        last = self._last_request_time.get(provider)
        if last is not None:
            elapsed = time.monotonic() - last
            if elapsed < self._rate_limit_gap:
                await asyncio.sleep(self._rate_limit_gap - elapsed)

    # ── Backoff ────────────────────────────────────────────────

    async def _backoff(self, attempt: int) -> None:
        """Exponential backoff with jitter."""
        delay = self._retry_delay * (2 ** attempt)
        jitter = random.uniform(0, delay * 0.1)
        await asyncio.sleep(delay + jitter)
