"""Centralized configuration (Settings) — single source of truth.

Environment variables with the ``SRGSSR_`` prefix populate the fields below.
Credentials are required for any tool call that hits the SRG SSR API; the
transport setting controls how :func:`srgssr_mcp.server.main` runs the MCP
server.
"""

import time
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

Transport = Literal["stdio", "sse", "streamable-http"]


class Settings(BaseSettings):
    """Centralized configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="SRGSSR_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    consumer_key: SecretStr = Field(
        default=SecretStr(""), validation_alias="SRGSSR_CONSUMER_KEY"
    )
    consumer_secret: SecretStr = Field(
        default=SecretStr(""), validation_alias="SRGSSR_CONSUMER_SECRET"
    )

    transport: Transport = Field(
        default="stdio",
        validation_alias="SRGSSR_MCP_TRANSPORT",
        description="MCP transport: 'stdio' (local), 'sse' or 'streamable-http' (remote).",
    )
    host: str = Field(default="127.0.0.1", validation_alias="SRGSSR_MCP_HOST")
    port: int = Field(default=8000, validation_alias="SRGSSR_MCP_PORT")
    mount_path: str | None = Field(default=None, validation_alias="SRGSSR_MCP_MOUNT_PATH")

    def require_credentials(self) -> tuple[str, str]:
        key = self.consumer_key.get_secret_value()
        secret = self.consumer_secret.get_secret_value()
        if not key or not secret:
            raise ValueError(
                "SRGSSR_CONSUMER_KEY and SRGSSR_CONSUMER_SECRET must be set. "
                "Register at https://developer.srgssr.ch to obtain credentials."
            )
        return key, secret


# SEC-013: bounded TTL instead of an unbounded lru_cache so rotated upstream
# credentials take effect without a process restart. Five minutes is a
# pragmatic balance between rotation latency and Settings construction cost.
SETTINGS_TTL_SECONDS = 300.0

_settings_cache: dict[str, Settings | float | None] = {
    "value": None,
    "loaded_at": 0.0,
}


def get_settings() -> Settings:
    """Return the process-wide :class:`Settings`, refreshing every ``SETTINGS_TTL_SECONDS``."""
    now = time.monotonic()
    cached = _settings_cache["value"]
    loaded_at = _settings_cache["loaded_at"]
    assert isinstance(loaded_at, float)
    if cached is None or (now - loaded_at) > SETTINGS_TTL_SECONDS:
        _settings_cache["value"] = Settings()
        _settings_cache["loaded_at"] = now
    return _settings_cache["value"]  # type: ignore[return-value]


def _clear_settings_cache() -> None:
    """Reset the cached Settings (test-only helper)."""
    _settings_cache["value"] = None
    _settings_cache["loaded_at"] = 0.0


# Backwards-compatible shim: existing tests call get_settings.cache_clear()
# (lru_cache convention). Keep the surface identical so nothing else needs
# to change in the test suite.
get_settings.cache_clear = _clear_settings_cache  # type: ignore[attr-defined]
