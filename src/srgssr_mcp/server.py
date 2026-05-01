"""SRG SSR MCP Server entry point.

Provides AI models with access to SRG SSR public APIs:
- SRF Weather (Swiss-wide forecasts)
- Video metadata (SRF, RTS, RSI, RTR, SWI)
- Audio metadata (radio shows and livestreams)
- EPG (Electronic Program Guide)
- Polis (Swiss votations and elections since 1900)

Authentication:
    Set SRGSSR_CONSUMER_KEY and SRGSSR_CONSUMER_SECRET as environment variables.
    Register at https://developer.srgssr.ch to obtain credentials.

Implementation lives in focused modules — :mod:`srgssr_mcp.config`,
:mod:`srgssr_mcp._http`, :mod:`srgssr_mcp._app` and the per-domain submodules
under :mod:`srgssr_mcp.tools`. This module just wires the entry points and
re-exports the public surface so callers (and tests) can keep importing from
``srgssr_mcp.server``.
"""

from mcp.server.fastmcp import FastMCP

from srgssr_mcp._app import PROTOCOL_VERSION, VALID_BU, BusinessUnit, ResponseFormat, mcp
from srgssr_mcp._http import (  # noqa: F401  (re-exported for backwards-compat)
    ALLOWED_HOSTS,
    AUDIO_BASE,
    BASE_URL,
    EPG_BASE,
    POLIS_BASE,
    TIMEOUT,
    TOKEN_URL,
    USER_AGENT,
    VIDEO_BASE,
    WEATHER_BASE,
    _api_get,
    _get_access_token,
    _get_credentials,
    _handle_error,
    _query_variants,
    _safe_api_get,
    _token_cache,
    _validate_url_safe,
)
from srgssr_mcp.config import Settings, Transport, get_settings  # noqa: F401

# Importing the tools package executes the registration decorators against
# ``mcp``; after this import all tools, resources and prompts are live.
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
from srgssr_mcp.tools.aggregation import DailyBriefingInput, srgssr_daily_briefing
from srgssr_mcp.tools.audio import (
    AudioEpisodesInput,
    srgssr_audio_get_episodes,
    srgssr_audio_get_livestreams,
    srgssr_audio_get_shows,
)
from srgssr_mcp.tools.epg import (  # noqa: F401  (_format_epg_programs re-exported)
    EpgProgramsInput,
    _format_epg_programs,
    srgssr_epg_get_programs,
)
from srgssr_mcp.tools.polis import (  # noqa: F401  (_format_votation_result re-exported)
    PolisListInput,
    PolisResultInput,
    _format_votation_result,
    srgssr_polis_get_elections,
    srgssr_polis_get_votation_results,
    srgssr_polis_get_votations,
)
from srgssr_mcp.tools.prompts import (
    analyse_abstimmungsverhalten_prompt,
    tagesbriefing_kanton_prompt,
)
from srgssr_mcp.tools.resources import epg_resource, votation_resource
from srgssr_mcp.tools.video import (
    VideoEpisodesInput,
    VideoLivestreamsInput,
    VideoShowsInput,
    srgssr_video_get_episodes,
    srgssr_video_get_livestreams,
    srgssr_video_get_shows,
)
from srgssr_mcp.tools.weather import (  # noqa: F401  (formatters re-exported)
    WeatherForecastInput,
    WeatherSearchInput,
    _format_7day_forecast,
    _format_current_weather,
    _format_hourly_forecast,
    srgssr_weather_current,
    srgssr_weather_forecast_7day,
    srgssr_weather_forecast_24h,
    srgssr_weather_search_location,
)

__all__ = [
    "ALLOWED_HOSTS",
    "AUDIO_BASE",
    "AudioEpisodesInput",
    "BASE_URL",
    "BusinessUnit",
    "DailyBriefingInput",
    "EPG_BASE",
    "EpgProgramsInput",
    "POLIS_BASE",
    "PROTOCOL_VERSION",
    "PolisListInput",
    "PolisResultInput",
    "ResponseFormat",
    "Settings",
    "TIMEOUT",
    "TOKEN_URL",
    "Transport",
    "USER_AGENT",
    "VALID_BU",
    "VIDEO_BASE",
    "VideoEpisodesInput",
    "VideoLivestreamsInput",
    "VideoShowsInput",
    "WEATHER_BASE",
    "WeatherForecastInput",
    "WeatherSearchInput",
    "analyse_abstimmungsverhalten_prompt",
    "epg_resource",
    "get_settings",
    "main",
    "mcp",
    "srgssr_audio_get_episodes",
    "srgssr_audio_get_livestreams",
    "srgssr_audio_get_shows",
    "srgssr_daily_briefing",
    "srgssr_epg_get_programs",
    "srgssr_polis_get_elections",
    "srgssr_polis_get_votation_results",
    "srgssr_polis_get_votations",
    "srgssr_video_get_episodes",
    "srgssr_video_get_livestreams",
    "srgssr_video_get_shows",
    "srgssr_weather_current",
    "srgssr_weather_forecast_24h",
    "srgssr_weather_forecast_7day",
    "srgssr_weather_search_location",
    "tagesbriefing_kanton_prompt",
    "votation_resource",
]


def _build_mcp(settings: Settings) -> FastMCP:
    """Apply transport-relevant settings to the module-level :data:`mcp`.

    Tools are registered against the module-level ``mcp`` instance at import
    time, so we mutate its host/port/mount_path here rather than constructing
    a fresh server. This keeps the lifespan setup identical across stdio and
    HTTP-style transports.
    """
    mcp.settings.host = settings.host
    mcp.settings.port = settings.port
    if settings.mount_path:
        mcp.settings.mount_path = settings.mount_path
    return mcp


def main() -> None:
    """Entry point for uvx / pip install. Transport selected via settings."""
    settings = get_settings()
    server = _build_mcp(settings)
    if settings.transport == "stdio":
        server.run(transport="stdio")
    else:
        server.run(transport=settings.transport, mount_path=settings.mount_path)


if __name__ == "__main__":
    main()
