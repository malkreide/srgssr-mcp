"""Module-level FastMCP server instance and shared enums.

The ``mcp`` instance lives here so that every tool/resource/prompt module can
import the same registry. Importing :mod:`srgssr_mcp.tools` (or any of its
submodules) executes the decorator-based registrations against this object.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from enum import StrEnum

from mcp.server.fastmcp import FastMCP
from mcp.shared.version import SUPPORTED_PROTOCOL_VERSIONS

from srgssr_mcp._http import close_http_client
from srgssr_mcp.logging_config import configure_logging, get_logger

configure_logging()
logger = get_logger()

# MCP spec revision this server is built and tested against. Pinned explicitly
# (rather than relying on the SDK default) so SDK upgrades cannot silently
# change wire-level behaviour. Bump together with a CHANGELOG entry whenever
# the target spec version moves.
PROTOCOL_VERSION = "2025-06-18"

if PROTOCOL_VERSION not in SUPPORTED_PROTOCOL_VERSIONS:
    raise RuntimeError(
        f"Pinned MCP protocolVersion {PROTOCOL_VERSION!r} is not in the installed "
        f"SDK's SUPPORTED_PROTOCOL_VERSIONS={SUPPORTED_PROTOCOL_VERSIONS}. "
        "Update PROTOCOL_VERSION (and CHANGELOG.md) or pin the SDK to a "
        "compatible version."
    )

VALID_BU = ["srf", "rts", "rsi", "rtr", "swi"]


class BusinessUnit(StrEnum):
    SRF = "srf"
    RTS = "rts"
    RSI = "rsi"
    RTR = "rtr"
    SWI = "swi"


class ResponseFormat(StrEnum):
    MARKDOWN = "markdown"
    JSON = "json"


@asynccontextmanager
async def lifespan(_server: FastMCP) -> AsyncIterator[None]:
    """Manage the shared httpx.AsyncClient lifetime (SDK-001).

    The HTTP client is created lazily on first use inside
    :mod:`srgssr_mcp._http`; this lifespan only owns its **shutdown** so
    sockets and the connection pool are cleaned up when the server stops
    (Ctrl-C, SIGTERM, transport disconnect).
    """
    try:
        yield
    finally:
        await close_http_client()


mcp = FastMCP(
    "srgssr_mcp",
    instructions=(
        "Provides access to SRG SSR public APIs covering Swiss weather, "
        "TV/radio metadata (SRF, RTS, RSI, RTR, SWI), program guides, and "
        "Swiss political data (votations and elections since 1900). "
        "All tools require valid SRGSSR_CONSUMER_KEY and SRGSSR_CONSUMER_SECRET."
    ),
    lifespan=lifespan,
)

logger.info("server_initialized", protocol_version=PROTOCOL_VERSION)
