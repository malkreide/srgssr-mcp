"""Module-level MCPServer server instance and shared enums.

The ``mcp`` instance lives here so that every tool/resource/prompt module can
import the same registry. Importing :mod:`srgssr_mcp.tools` (or any of its
submodules) executes the decorator-based registrations against this object.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from enum import StrEnum

from mcp.server.caching import CacheableMethod, CacheHint
from mcp.server.mcpserver import MCPServer
from mcp.types.version import SUPPORTED_PROTOCOL_VERSIONS

from srgssr_mcp._http import close_http_client
from srgssr_mcp.logging_config import configure_logging, get_logger

configure_logging()
logger = get_logger()

# MCP spec revision this server is built and tested against. Pinned explicitly
# (rather than relying on the SDK default) so SDK upgrades cannot silently
# change wire-level behaviour. Bump together with a CHANGELOG entry whenever
# the target spec version moves.
# Der Pin stand auf "2025-06-18", waehrend das SDK "2026-07-28" aushandelt.
# Der Schutz darunter hat das nicht gemeldet, und er kann es strukturell nicht:
# `SUPPORTED_PROTOCOL_VERSIONS` ist rueckwaertskompatibel und enthaelt noch
# "2024-11-05". Eine Mitgliedschaftspruefung gegen diese Liste ist damit
# erfuellt, solange die Revision nicht ganz entfernt wird — sie faengt einen
# Wegfall ab, aber keine Drift. Genau dafuer gibt es jetzt zusaetzlich
# `tests/test_protocol_version.py` gegen `LATEST_PROTOCOL_VERSION`.
PROTOCOL_VERSION = "2026-07-28"

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
async def lifespan(_server: MCPServer) -> AsyncIterator[None]:
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


# SEP-2549, Spec 2026-07-28: die auflistenden Methoden tragen `ttlMs` und
# `cacheScope`. Das SDK setzt beides auf «sofort veraltet, nie geteilt» — ein
# Server ohne `cache_hints` verhaelt sich also nicht neutral, sondern laesst
# jeden Client bei jeder Verbindung neu auflisten, fuer Verzeichnisse, die beim
# Import feststehen und sich zur Laufzeit des Prozesses nicht aendern koennen.
#
# `public` folgt aus der Sache, nicht aus Bequemlichkeit: die 10 Tools werden
# per Dekorator beim Import registriert, es gibt keine Filterung nach Aufrufer.
# Sobald eine Liste vom Aufrufer abhaengt, muss der Scope im selben Commit auf
# `private` wechseln.
#
# `resources/read` und `prompts/get` stehen bewusst nicht dabei: das waere eine
# Zusicherung ueber den INHALT statt ueber das Verzeichnis.
LIST_CACHE_TTL_MS = 300_000

# Annotiert, nicht inferiert: `MCPServer` nimmt
# `Mapping[CacheableMethod, CacheHint]`, und ein Dict-Literal ohne Annotation
# inferiert mypy als `str`. Zur Laufzeit stimmt beides — ein `mypy src/`-Gate
# meldet den Unterschied, die Tests nicht.
CACHE_HINTS: dict[CacheableMethod, CacheHint] = {
    "tools/list": CacheHint(ttl_ms=LIST_CACHE_TTL_MS, scope="public"),
    "resources/list": CacheHint(ttl_ms=LIST_CACHE_TTL_MS, scope="public"),
    "resources/templates/list": CacheHint(ttl_ms=LIST_CACHE_TTL_MS, scope="public"),
    "prompts/list": CacheHint(ttl_ms=LIST_CACHE_TTL_MS, scope="public"),
    "server/discover": CacheHint(ttl_ms=LIST_CACHE_TTL_MS, scope="public"),
}

mcp = MCPServer(
    "srgssr_mcp",
    cache_hints=CACHE_HINTS,
    instructions=(
        "Provides access to SRG SSR public APIs covering Swiss weather, "
        "TV/radio metadata (SRF, RTS, RSI, RTR, SWI), program guides, and "
        "Swiss political data (votations and elections since 1900). "
        "All tools require valid SRGSSR_CONSUMER_KEY and SRGSSR_CONSUMER_SECRET."
    ),
    lifespan=lifespan,
)

logger.info("server_initialized", protocol_version=PROTOCOL_VERSION)
