"""Aggregation tools (ARCH-007).

The thin-wrapper tools each cover one upstream endpoint and return atomic
responses. Aggregation tools fan out across multiple endpoints in parallel via
:func:`asyncio.gather` and merge the results, so callers don't have to chain
three roundtrips for cross-domain queries (e.g. "what's the weather and what's
on TV in Zurich tonight?"). When one upstream fails the other section is still
rendered so the response degrades gracefully.
"""

import asyncio
import json

from pydantic import BaseModel, ConfigDict, Field

from srgssr_mcp._app import BusinessUnit, ResponseFormat, mcp
from srgssr_mcp._http import EPG_BASE, WEATHER_BASE, _safe_api_get
from srgssr_mcp.tools.epg import _format_epg_programs
from srgssr_mcp.tools.weather import _format_hourly_forecast


class DailyBriefingInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    business_unit: BusinessUnit = Field(
        ...,
        description="SRG SSR Unternehmenseinheit für das EPG: 'srf', 'rts' oder 'rsi' (RTR/SWI ohne EPG)",
    )
    channel_id: str = Field(
        ...,
        description="Kanal-ID aus srgssr_video_get_livestreams (z.B. 'srf1', 'rts1', 'rsi-la1')",
        min_length=1,
        max_length=100,
    )
    date: str = Field(
        ...,
        description="Datum im Format YYYY-MM-DD (z.B. '2026-04-30')",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    )
    latitude: float = Field(
        ...,
        description="Breitengrad des Schweizer Standorts (45.8–47.9)",
        ge=45.8,
        le=47.9,
    )
    longitude: float = Field(
        ...,
        description="Längengrad des Schweizer Standorts (5.9–10.5)",
        ge=5.9,
        le=10.5,
    )
    geolocation_id: str | None = Field(
        default=None,
        description="Optionale geolocationId aus srgssr_weather_search_location für präzisere Vorhersagen",
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Ausgabeformat: 'markdown' oder 'json'",
    )


@mcp.tool(
    name="srgssr_daily_briefing",
    description=(
        "Aggregiertes Tagesbriefing: kombiniert die 24-Stunden-Wettervorhersage von "
        "SRF Meteo mit dem EPG-Tagesprogramm eines SRG SSR TV- oder Radiosenders. "
        "Beide Datenquellen werden parallel abgerufen (asyncio.gather), so dass "
        "ein einzelner Tool-Call genügt statt zweier sequentieller Roundtrips.\n\n"
        "<use_case>«Wetter + Programm für heute Abend»: Abendplanung, redaktionelle "
        "Tages-Briefings, Newsletter-Generierung oder Voice-Assistant-Antworten, "
        "die Wetterlage und TV-/Radio-Programm in einem Schwung benötigen. Spart "
        "gegenüber den Einzeltools srgssr_weather_forecast_24h und "
        "srgssr_epg_get_programs einen Roundtrip und liefert ein konsistent "
        "formatiertes Ergebnis.</use_case>\n\n"
        "<important_notes>EPG nur für SRF, RTS und RSI verfügbar — RTR/SWI führen "
        "in einer Teil-Fehlermeldung. Wetterdaten beschränkt auf Schweizer "
        "Koordinaten (Latitude 45.8–47.9, Longitude 5.9–10.5). Bei Ausfall einer "
        "der beiden Quellen wird die andere Sektion trotzdem gerendert (Graceful "
        "Degradation); die Fehlerursache wird in der entsprechenden Sektion "
        "gemeldet.</important_notes>\n\n"
        "<example>business_unit='srf', channel_id='srf1', date='2026-04-30', "
        "latitude=47.3769, longitude=8.5417 | business_unit='rts', "
        "channel_id='rts1', date='2026-05-01', latitude=46.5197, longitude=6.6323, "
        "geolocation_id='100456'</example>"
    ),
    annotations={
        "title": "SRG SSR – Tagesbriefing (Wetter + EPG)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def srgssr_daily_briefing(params: DailyBriefingInput) -> str:
    """Combines weather forecast (24h) and EPG programs for a day in a single call.

    Both upstream calls run concurrently via :func:`asyncio.gather`. If one of
    them fails the other is still returned, with the failure surfaced inline.
    """
    weather_query: dict = {
        "latitude": params.latitude,
        "longitude": params.longitude,
    }
    if params.geolocation_id:
        weather_query["geolocationId"] = params.geolocation_id

    epg_query = {
        "bu": params.business_unit.value,
        "channel": params.channel_id,
        "date": params.date,
    }
    epg_hint = (
        f"channel_id='{params.channel_id}' nicht gefunden für "
        f"business_unit='{params.business_unit.value}'. EPG ist nur für SRF, RTS "
        f"und RSI verfügbar; Kanal-IDs über srgssr_video_get_livestreams oder "
        f"srgssr_audio_get_livestreams verifizieren."
    )

    weather_result, epg_result = await asyncio.gather(
        _safe_api_get(f"{WEATHER_BASE}/24hour", params=weather_query),
        _safe_api_get(f"{EPG_BASE}/programs", params=epg_query, not_found_hint=epg_hint),
    )

    if params.response_format == ResponseFormat.JSON:
        return json.dumps(
            {
                "date": params.date,
                "channel_id": params.channel_id,
                "business_unit": params.business_unit.value,
                "weather": weather_result,
                "epg": (
                    epg_result.get("programList", epg_result.get("programs", []))
                    if isinstance(epg_result, dict)
                    else epg_result
                ),
            },
            indent=2,
            ensure_ascii=False,
        )

    bu = params.business_unit.value
    lines = [
        f"# Tagesbriefing – {params.channel_id.upper()} ({bu.upper()}) am {params.date}\n",
        "## Wetter (24h)",
    ]
    if isinstance(weather_result, dict):
        lines.append(_format_hourly_forecast(weather_result))
    else:
        lines.append(weather_result)

    lines.append("\n## TV-/Radioprogramm")
    if isinstance(epg_result, dict):
        programs = epg_result.get("programList", epg_result.get("programs", []))
        lines.append(_format_epg_programs(programs, params.channel_id, bu, params.date))
    else:
        lines.append(epg_result)

    return "\n".join(lines)
