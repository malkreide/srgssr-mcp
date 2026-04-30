"""SRG SSR MCP tools, resources and prompts.

Importing this package executes the @mcp.tool/@mcp.resource/@mcp.prompt
decorators on the shared :data:`srgssr_mcp._app.mcp` instance, so listing
or calling primitives through that instance reflects everything below.
"""

from srgssr_mcp.tools import (  # noqa: F401  (import for side-effect: registration)
    aggregation,
    audio,
    epg,
    polis,
    prompts,
    resources,
    video,
    weather,
)
