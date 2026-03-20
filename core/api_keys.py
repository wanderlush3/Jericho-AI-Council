"""
Jericho — Secure API Key Manager (F-023)

Encrypt API keys at rest using Fernet (AES-128-CBC) and store them
in the project's ``config/.env`` file.  Keys are derived from
machine-specific data so they never need to be shared or remembered.

Usage::

    mgr = APIKeyManager()
    mgr.save_key("openrouter", "sk-abc123...")
    key = mgr.load_key("openrouter")   # decrypted
    status = mgr.key_status("openrouter")
    # {"configured": True, "masked": "sk-a…23"}
"""

from __future__ import annotations

import base64
import hashlib
import os
import re
import socket
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from config.settings import (
    DEFAULT_MANCER_MODEL,
    DEFAULT_OPENROUTER_MODEL,
    ENV_FILE,
    MANCER_API_KEY_ENV,
    MANCER_MODEL_ENV,
    OPENROUTER_API_KEY_ENV,
    OPENROUTER_MODEL_ENV,
    USER_DESCRIPTION_ENV,
    USER_DESCRIPTION_MAX_LENGTH,
)

# ─── Constants ─────────────────────────────────────────────────

_PROVIDER_ENV_MAP: dict[str, str] = {
    "openrouter": OPENROUTER_API_KEY_ENV,
    "mancer": MANCER_API_KEY_ENV,
}

_PROVIDER_MODEL_ENV_MAP: dict[str, str] = {
    "openrouter": OPENROUTER_MODEL_ENV,
    "mancer": MANCER_MODEL_ENV,
}

_PROVIDER_MODEL_DEFAULTS: dict[str, str] = {
    "openrouter": DEFAULT_OPENROUTER_MODEL,
    "mancer": DEFAULT_MANCER_MODEL,
}

# Fernet tokens are base64url and always start with "gAAAAA"
_FERNET_PREFIX = "gAAAAA"


# ─── Key Derivation ───────────────────────────────────────────


def _derive_fernet_key() -> bytes:
    """
    Derive a stable, machine-specific Fernet key.

    Uses hostname + OS login name as salt material run through
    PBKDF2-HMAC-SHA256 to produce a 32-byte key that is then
    base64url-encoded for Fernet.
    """
    hostname = socket.gethostname()
    try:
        username = os.getlogin()
    except OSError:
        username = os.environ.get("USERNAME", os.environ.get("USER", "jericho"))

    salt = f"jericho-api-keys-{hostname}-{username}".encode()
    raw = hashlib.pbkdf2_hmac("sha256", b"jericho-seal", salt, iterations=100_000)
    return base64.urlsafe_b64encode(raw)


# ─── Manager ──────────────────────────────────────────────────


class APIKeyManager:
    """Encrypt, store, and load API keys from the project ``.env`` file."""

    PROVIDERS = tuple(_PROVIDER_ENV_MAP.keys())

    def __init__(self, env_path: Path | None = None) -> None:
        self._env_path = env_path or ENV_FILE
        self._fernet = Fernet(_derive_fernet_key())

    # ── Public API ────────────────────────────────────────────

    def save_key(self, provider: str, raw_key: str) -> dict[str, Any]:
        """
        Encrypt *raw_key* and persist it to the ``.env`` file.

        Returns the same shape as :meth:`key_status`.
        """
        provider = provider.lower()
        env_var = self._env_var_for(provider)
        encrypted = self._fernet.encrypt(raw_key.encode()).decode()

        lines = self._read_env_lines()
        lines = self._upsert_line(lines, env_var, encrypted)
        self._write_env_lines(lines)

        # Also set in this process so APIClient picks it up
        os.environ[env_var] = raw_key

        return {
            "provider": provider,
            "configured": True,
            "masked": self.mask_key(raw_key),
        }

    def load_key(self, provider: str) -> str | None:
        """
        Read and decrypt the key for *provider*.

        Returns ``None`` if no key is configured.  Also sets the
        corresponding environment variable so downstream code
        (e.g. ``APIClient``) picks it up.
        """
        provider = provider.lower()
        env_var = self._env_var_for(provider)
        value = self._read_env_value(env_var)

        if not value or value.startswith("your-"):
            return None

        # Decrypt if encrypted
        if value.startswith(_FERNET_PREFIX):
            try:
                decrypted = self._fernet.decrypt(value.encode()).decode()
            except InvalidToken:
                return None
            os.environ[env_var] = decrypted
            return decrypted

        # Legacy plain-text key — still works, just not encrypted
        os.environ[env_var] = value
        return value

    def load_all(self) -> dict[str, str | None]:
        """Load and decrypt all provider keys.  Called at startup."""
        return {p: self.load_key(p) for p in self.PROVIDERS}

    def delete_key(self, provider: str) -> dict[str, Any]:
        """Remove a configured key entirely."""
        provider = provider.lower()
        env_var = self._env_var_for(provider)

        lines = self._read_env_lines()
        lines = self._upsert_line(lines, env_var, f"your-{provider}-key-here")
        self._write_env_lines(lines)

        os.environ.pop(env_var, None)

        return {
            "provider": provider,
            "configured": False,
            "masked": None,
        }

    def key_status(self, provider: str) -> dict[str, Any]:
        """
        Return configuration status for *provider* **without**
        exposing the raw key.
        """
        provider = provider.lower()
        env_var = self._env_var_for(provider)
        value = self._read_env_value(env_var)

        if not value or value.startswith("your-"):
            return {"provider": provider, "configured": False, "masked": None}

        # Decrypt to get the masked version
        if value.startswith(_FERNET_PREFIX):
            try:
                decrypted = self._fernet.decrypt(value.encode()).decode()
            except InvalidToken:
                return {"provider": provider, "configured": False, "masked": None}
            return {
                "provider": provider,
                "configured": True,
                "masked": self.mask_key(decrypted),
            }

        # Legacy plain-text key
        return {
            "provider": provider,
            "configured": True,
            "masked": self.mask_key(value),
        }

    def all_status(self) -> list[dict[str, Any]]:
        """Status for every provider."""
        return [self.key_status(p) for p in self.PROVIDERS]

    # ── Model Management ─────────────────────────────────────

    def save_model(self, provider: str, model_name: str) -> dict[str, Any]:
        """
        Save the model name for *provider* to the ``.env`` file.

        Model names are stored in plain text (not encrypted) since
        they are not sensitive.
        """
        provider = provider.lower()
        env_var = self._model_env_var_for(provider)

        lines = self._read_env_lines()
        lines = self._upsert_line(lines, env_var, model_name)
        self._write_env_lines(lines)

        os.environ[env_var] = model_name

        return {
            "provider": provider,
            "model": model_name,
        }

    def load_model(self, provider: str) -> str:
        """
        Read the configured model for *provider*.

        Falls back to the default model if not configured.
        """
        provider = provider.lower()
        env_var = self._model_env_var_for(provider)
        value = self._read_env_value(env_var)

        if value:
            os.environ[env_var] = value
            return value

        return _PROVIDER_MODEL_DEFAULTS.get(provider, "")

    def model_status(self, provider: str) -> dict[str, Any]:
        """Return the configured model for *provider*."""
        provider = provider.lower()
        model = self.load_model(provider)
        default = _PROVIDER_MODEL_DEFAULTS.get(provider, "")
        return {
            "provider": provider,
            "model": model,
            "is_default": model == default,
        }

    def all_model_status(self) -> list[dict[str, Any]]:
        """Model status for every provider."""
        return [self.model_status(p) for p in self.PROVIDERS]

    def _model_env_var_for(self, provider: str) -> str:
        env_var = _PROVIDER_MODEL_ENV_MAP.get(provider)
        if env_var is None:
            raise ValueError(
                f"Unknown provider '{provider}'. "
                f"Valid providers: {', '.join(self.PROVIDERS)}"
            )
        return env_var

    # ── User Description ─────────────────────────────────────

    def get_user_description(self) -> str:
        """Read the user's self-description from the ``.env`` file."""
        value = self._read_env_value(USER_DESCRIPTION_ENV)
        return value or ""

    def save_user_description(self, text: str) -> dict[str, Any]:
        """Save the user's self-description to the ``.env`` file.

        Raises ``ValueError`` if the text exceeds the maximum length.
        """
        text = text.strip()
        if len(text) > USER_DESCRIPTION_MAX_LENGTH:
            raise ValueError(
                f"Description exceeds {USER_DESCRIPTION_MAX_LENGTH} "
                f"characters (got {len(text)})"
            )
        lines = self._read_env_lines()
        lines = self._upsert_line(lines, USER_DESCRIPTION_ENV, text)
        self._write_env_lines(lines)
        return {"description": text}

    # ── Masking ───────────────────────────────────────────────

    @staticmethod
    def mask_key(raw_key: str) -> str:
        """
        Obfuscate a key showing first 4 and last 2 characters.

        ``"sk-abc123xyz"`` → ``"sk-a…yz"``
        """
        if len(raw_key) <= 6:
            return "••••"
        return f"{raw_key[:4]}…{raw_key[-2:]}"

    # ── Internal Helpers ──────────────────────────────────────

    def _env_var_for(self, provider: str) -> str:
        env_var = _PROVIDER_ENV_MAP.get(provider)
        if env_var is None:
            raise ValueError(
                f"Unknown provider '{provider}'. "
                f"Valid providers: {', '.join(self.PROVIDERS)}"
            )
        return env_var

    def _read_env_lines(self) -> list[str]:
        if not self._env_path.exists():
            return []
        return self._env_path.read_text(encoding="utf-8").splitlines()

    def _write_env_lines(self, lines: list[str]) -> None:
        self._env_path.parent.mkdir(parents=True, exist_ok=True)
        self._env_path.write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )

    def _read_env_value(self, env_var: str) -> str | None:
        """Read a single value from the .env file (not os.environ)."""
        for line in self._read_env_lines():
            stripped = line.strip()
            if stripped.startswith("#") or "=" not in stripped:
                continue
            key, _, value = stripped.partition("=")
            if key.strip() == env_var:
                return value.strip()
        return None

    @staticmethod
    def _upsert_line(
        lines: list[str], env_var: str, value: str
    ) -> list[str]:
        """Update an existing line or append a new one."""
        pattern = re.compile(rf"^\s*{re.escape(env_var)}\s*=")
        found = False
        result: list[str] = []
        for line in lines:
            if pattern.match(line):
                result.append(f"{env_var}={value}")
                found = True
            else:
                result.append(line)
        if not found:
            result.append(f"{env_var}={value}")
        return result
