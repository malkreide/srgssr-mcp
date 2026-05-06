"""Centralized configuration (Settings) — single source of truth.

Environment variables with the ``SRGSSR_`` prefix populate the fields below.
Credentials are required for any tool call that hits the SRG SSR API; the
transport setting controls how :func:`srgssr_mcp.server.main` runs the MCP
server.
"""

from functools import lru_cache
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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide :class:`Settings` instance (memoized)."""
    return Settings()
