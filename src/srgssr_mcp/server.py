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
    AudioShowsInput,
    srgssr_audio_get_episodes,
    srgssr_audio_get_livestreams,
    srgssr_audio_get_shows,
)
from srgssr_mcp.tools.epg import (
    EpgProgramsInput,
    srgssr_epg_get_programs,
)
from srgssr_mcp.tools.polis import (
    PolisListInput,
    PolisResultInput,
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
from srgssr_mcp.tools.weather import (
    WeatherForecastInput,
    WeatherSearchInput,
    srgssr_weather_current,
    srgssr_weather_forecast_7day,
    srgssr_weather_forecast_24h,
    srgssr_weather_search_location,
)

__all__ = [
    "ALLOWED_HOSTS",
    "AUDIO_BASE",
    "AudioEpisodesInput",
    "AudioShowsInput",
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


def _transport_kwargs(settings: Settings) -> dict[str, object]:
    """Build the per-transport ``run()`` kwargs from :class:`Settings`.

    mcp 2.x removed host/port/mount_path from ``MCPServer.settings``; they are
    ``run()`` arguments now, so there is nothing left to mutate on the
    module-level :data:`mcp` (tools are still registered against it at import
    time). Assigning them would raise ``ValueError`` rather than be ignored.

    ``mount_path`` has no 2.x counterpart. In 1.x it only rewrote the message
    endpoint *advertised* to the client while the routes stayed unprefixed —
    correct only when an outer ASGI app mounted the server under that prefix.
    2.x uses one value for both, so ``SRGSSR_MCP_MOUNT_PATH`` maps to
    ``message_path``, which moves the route as well. For ``streamable-http``
    the setting was already ignored in 1.x (``run()`` never forwarded it to
    ``run_streamable_http_async``), so it stays ignored here — passing it would
    now be a ``TypeError`` instead of a silent no-op.
    """
    if settings.transport == "stdio":
        return {}
    kwargs: dict[str, object] = {"host": settings.host, "port": settings.port}
    if settings.transport == "sse" and settings.mount_path:
        prefix = settings.mount_path.rstrip("/")
        kwargs["message_path"] = f"{prefix}/messages/"
    return kwargs


def main() -> None:
    """Entry point for uvx / pip install. Transport selected via settings."""
    settings = get_settings()
    mcp.run(transport=settings.transport, **_transport_kwargs(settings))


if __name__ == "__main__":
    main()
