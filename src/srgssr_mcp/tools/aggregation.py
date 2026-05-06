"""Aggregation tools (ARCH-007).

The thin-wrapper tools each cover one upstream endpoint and return atomic
responses. Aggregation tools fan out across multiple endpoints in parallel via
:func:`asyncio.gather` and merge the results, so callers don't have to chain
roundtrips for cross-domain queries (e.g. "what's the weather and what's
on TV in Zurich tonight?"). When one upstream fails the other section is still
returned so the response degrades gracefully.

After SDK-002 Option A: the aggregator delegates to the typed leaf tools
(``srgssr_weather_forecast_24h`` and ``srgssr_epg_get_programs``) instead of
calling ``_safe_api_get`` directly. That gives us the per-cluster
``ToolErrorResponse`` graceful-degradation contract for free, plus typed
sub-responses inside :class:`DailyBriefingResponse`.
"""

import asyncio

from mcp.server.fastmcp import Context
from pydantic import BaseModel, ConfigDict, Field

from srgssr_mcp._app import BusinessUnit, mcp
from srgssr_mcp._models import DailyBriefingResponse, ToolErrorResponse
from srgssr_mcp.logging_config import get_logger
from srgssr_mcp.tools.epg import EpgProgramsInput, srgssr_epg_get_programs
from srgssr_mcp.tools.weather import WeatherForecastInput, srgssr_weather_forecast_24h

logger = get_logger("mcp.srgssr.aggregation")


class DailyBriefingInput(BaseModel):
    model_config = ConfigDict(strict=True, str_strip_whitespace=True, extra="forbid")
    business_unit: BusinessUnit = Field(
        ...,
        description="SRG SSR Unternehmenseinheit für das EPG: 'srf', 'rts' oder 'rsi' (RTR/SWI ohne EPG)",
    )
    channel_id: str = Field(
        ..., min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$"
    )
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    latitude: float = Field(..., ge=45.8, le=47.9)
    longitude: float = Field(..., ge=5.9, le=10.5)
    geolocation_id: str | None = Field(
        default=None, min_length=1, max_length=50, pattern=r"^[A-Za-z0-9_-]+$"
    )


@mcp.tool(
    name="srgssr_daily_briefing",
    description=(
        "Aggregiertes Tagesbriefing: kombiniert die 24-Stunden-Wettervorhersage "
        "von SRF Meteo mit dem EPG-Tagesprogramm eines SRG SSR TV- oder "
        "Radiosenders. Beide Datenquellen werden parallel abgerufen "
        "(asyncio.gather), so dass ein einzelner Tool-Call genügt statt "
        "zweier sequentieller Roundtrips.\n\n"
        "<use_case>«Wetter + Programm für heute Abend»: Abendplanung, "
        "redaktionelle Tages-Briefings.</use_case>\n\n"
        "<important_notes>EPG nur für SRF, RTS und RSI. Bei Ausfall einer "
        "der beiden Quellen wird die andere Sektion trotzdem geliefert "
        "(Graceful Degradation) — das Feld enthält dann ein "
        "ToolErrorResponse.</important_notes>\n\n"
        "<example>business_unit='srf', channel_id='srf1', date='2026-04-30', "
        "latitude=47.3769, longitude=8.5417</example>"
    ),
    annotations={
        "title": "SRG SSR – Tagesbriefing (Wetter + EPG)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def srgssr_daily_briefing(
    params: DailyBriefingInput,
    ctx: Context | None = None,
) -> DailyBriefingResponse:
    """Compose a day's weather + EPG into one typed response.

    The two leaf tools each catch their own exceptions and return either a
    success Response or a :class:`ToolErrorResponse`, so this aggregator
    never raises and always assembles a DailyBriefingResponse — keeping the
    Graceful-Degradation contract from before the typed-model migration.
    """
    log = logger.bind(
        tool="srgssr_daily_briefing",
        business_unit=params.business_unit.value,
        channel_id=params.channel_id,
        date=params.date,
        latitude=params.latitude,
        longitude=params.longitude,
        geolocation_id=params.geolocation_id,
    )
    log.info("tool_invoked")
    if ctx is not None:
        await ctx.info(
            "srgssr_daily_briefing invoked",
            business_unit=params.business_unit.value,
            channel_id=params.channel_id,
            date=params.date,
        )
        await ctx.report_progress(
            0.0, total=2.0, message="Wetter und EPG parallel abrufen"
        )

    weather_input = WeatherForecastInput(
        latitude=params.latitude,
        longitude=params.longitude,
        geolocation_id=params.geolocation_id,
    )
    epg_input = EpgProgramsInput(
        business_unit=params.business_unit,
        channel_id=params.channel_id,
        date=params.date,
    )

    weather_resp, epg_resp = await asyncio.gather(
        srgssr_weather_forecast_24h(weather_input),
        srgssr_epg_get_programs(epg_input),
    )

    if ctx is not None:
        await ctx.report_progress(
            2.0, total=2.0, message="Beide Quellen geladen, Antwort rendern"
        )

    log.info(
        "tool_succeeded",
        weather_ok=not isinstance(weather_resp, ToolErrorResponse),
        epg_ok=not isinstance(epg_resp, ToolErrorResponse),
    )

    return DailyBriefingResponse(
        business_unit=params.business_unit.value,
        channel_id=params.channel_id,
        date=params.date,
        weather=weather_resp,
        epg=epg_resp,
    )
