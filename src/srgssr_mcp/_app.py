"""Module-level FastMCP server instance and shared enums.

The ``mcp`` instance lives here so that every tool/resource/prompt module can
import the same registry. Importing :mod:`srgssr_mcp.tools` (or any of its
submodules) executes the decorator-based registrations against this object.
"""

from enum import StrEnum

from mcp.server.fastmcp import FastMCP

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


mcp = FastMCP(
    "srgssr_mcp",
    instructions=(
        "Provides access to SRG SSR public APIs covering Swiss weather, "
        "TV/radio metadata (SRF, RTS, RSI, RTR, SWI), program guides, and "
        "Swiss political data (votations and elections since 1900). "
        "All tools require valid SRGSSR_CONSUMER_KEY and SRGSSR_CONSUMER_SECRET."
    ),
)
