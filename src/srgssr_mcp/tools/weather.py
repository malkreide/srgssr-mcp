"""SRF Meteo tools: location search, current weather, 24h and 7-day forecasts."""

from mcp.server.fastmcp import Context
from pydantic import BaseModel, ConfigDict, Field

from srgssr_mcp._app import mcp
from srgssr_mcp._http import WEATHER_BASE, _api_get, _build_error_response, _query_variants
from srgssr_mcp._models import (
    ToolErrorResponse,
    WeatherCurrent,
    WeatherCurrentResponse,
    WeatherDay,
    WeatherForecast7dayResponse,
    WeatherForecast24hResponse,
    WeatherHour,
    WeatherLocation,
    WeatherLocationsResponse,
)
from srgssr_mcp.logging_config import get_logger

logger = get_logger("mcp.srgssr.weather")


class WeatherSearchInput(BaseModel):
    model_config = ConfigDict(strict=True, str_strip_whitespace=True, extra="forbid")
    query: str = Field(
        ...,
        description="Ortname oder Postleitzahl in der Schweiz (z.B. 'Zürich', '8001', 'Luzern')",
        min_length=2,
        max_length=100,
        pattern=r"^[\w\s.\-']+$",
    )


class WeatherForecastInput(BaseModel):
    model_config = ConfigDict(strict=True, str_strip_whitespace=True, extra="forbid")
    latitude: float = Field(
        ...,
        description="Geografische Breite (z.B. 47.3769 für Zürich)",
        ge=45.8,
        le=47.9,
    )
    longitude: float = Field(
        ...,
        description="Geografische Länge (z.B. 8.5417 für Zürich)",
        ge=5.9,
        le=10.5,
    )
    geolocation_id: str | None = Field(
        default=None,
        description="Optionale geolocationId aus srgssr_weather_search_location für präzisere Vorhersagen",
        min_length=1,
        max_length=50,
        pattern=r"^[A-Za-z0-9_-]+$",
    )


@mcp.tool(
    name="srgssr_weather_search_location",
    description=(
        "Sucht Schweizer Standorte für die Wettervorhersage nach Name oder Postleitzahl "
        "und gibt eine Liste von Orten mit geolocationId zurück.\n\n"
        "<use_case>Wetteranalysen, Reiseplanung und journalistische Recherchen zu "
        "Schweizer Standorten. Erster Schritt vor srgssr_weather_current, "
        "srgssr_weather_forecast_24h oder srgssr_weather_forecast_7day, um die "
        "präzise geolocationId für eine Vorhersage zu ermitteln.</use_case>\n\n"
        "<important_notes>Beschränkt auf Schweizer Standorte (SRF Meteo). Die "
        "zurückgelieferte geolocationId verbessert die Qualität der Wettervorhersagen "
        "gegenüber reinen Koordinaten.</important_notes>\n\n"
        "<example>query='Zürich' | query='8001' | query='Lausanne'</example>"
    ),
    annotations={
        "title": "SRF Meteo – Standort suchen",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def srgssr_weather_search_location(
    params: WeatherSearchInput,
    ctx: Context | None = None,
) -> WeatherLocationsResponse | ToolErrorResponse:
    """Search Swiss locations for weather forecasting (SDK-002 strict model)."""
    log = logger.bind(tool="srgssr_weather_search_location", query=params.query)
    log.info("tool_invoked")
    if ctx is not None:
        await ctx.info(
            "srgssr_weather_search_location invoked", query=params.query
        )
    raw_locations: list = []
    matched_variant = params.query
    tried: list[str] = []
    try:
        for variant in _query_variants(params.query):
            tried.append(variant)
            data = await _api_get(
                f"{WEATHER_BASE}/geolocations",
                params={"searchterm": variant},
            )
            raw_locations = data.get("geolocationList", [])
            if raw_locations:
                matched_variant = variant
                break
    except Exception as e:
        log.error("tool_failed", error_type=type(e).__name__, error=str(e), tried=tried)
        return _build_error_response(e)

    log.info(
        "tool_succeeded",
        result_count=len(raw_locations),
        matched_variant=matched_variant,
        variants_tried=len(tried),
    )

    locations = [WeatherLocation.model_validate(loc) for loc in raw_locations]
    return WeatherLocationsResponse(
        query=params.query,
        matched_variant=matched_variant,
        tried=tried,
        locations=locations,
        count=len(locations),
    )


def _extract_value(values: dict, key: str) -> float | int | None:
    """Pluck the ``value`` from SRF Meteo's nested ``{key: {value: x}}`` shape."""
    entry = values.get(key)
    if isinstance(entry, dict):
        return entry.get("value")
    return None


@mcp.tool(
    name="srgssr_weather_current",
    description=(
        "Liefert die aktuelle Wettersituation von SRF Meteo für einen Schweizer Standort "
        "(Temperatur, Wettercode, Wind, Niederschlag, Luftfeuchtigkeit).\n\n"
        "<use_case>Echtzeit-Wetterabfragen für Outdoor-Aktivitäten, Verkehrsmeldungen, "
        "Energieprognosen oder kontextuelle Anreicherung von redaktionellen "
        "Inhalten.</use_case>\n\n"
        "<important_notes>Nur für Schweizer Standorte (Latitude 45.8–47.9, Longitude "
        "5.9–10.5). geolocation_id aus srgssr_weather_search_location empfohlen.</important_notes>\n\n"
        "<example>latitude=47.3769, longitude=8.5417 (Zürich)</example>"
    ),
    annotations={
        "title": "SRF Meteo – Aktuelles Wetter",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def srgssr_weather_current(
    params: WeatherForecastInput,
    ctx: Context | None = None,
) -> WeatherCurrentResponse | ToolErrorResponse:
    """Current weather for a Swiss location (SDK-002 strict model)."""
    log = logger.bind(
        tool="srgssr_weather_current",
        latitude=params.latitude,
        longitude=params.longitude,
        geolocation_id=params.geolocation_id,
    )
    log.info("tool_invoked")
    if ctx is not None:
        await ctx.info(
            "srgssr_weather_current invoked",
            latitude=params.latitude,
            longitude=params.longitude,
        )
    try:
        query_params: dict = {
            "latitude": params.latitude,
            "longitude": params.longitude,
        }
        if params.geolocation_id:
            query_params["geolocationId"] = params.geolocation_id
        data = await _api_get(f"{WEATHER_BASE}/current", params=query_params)
    except Exception as e:
        log.error("tool_failed", error_type=type(e).__name__, error=str(e))
        return _build_error_response(e)

    log.info("tool_succeeded")

    fc = data.get("currentForecast", data) or {}
    values = fc.get("values", {}) if isinstance(fc, dict) else {}
    current = WeatherCurrent(
        temperature_c=_extract_value(values, "ttt"),
        weather_code=_extract_value(values, "weatherCode"),
        wind_speed_kmh=_extract_value(values, "ff"),
        wind_direction_deg=_extract_value(values, "dd"),
        precipitation_mm=_extract_value(values, "rr"),
        relative_humidity_pct=_extract_value(values, "relhum"),
    )
    return WeatherCurrentResponse(
        latitude=params.latitude,
        longitude=params.longitude,
        geolocation_id=params.geolocation_id,
        current=current,
    )


@mcp.tool(
    name="srgssr_weather_forecast_24h",
    description=(
        "Liefert die stündliche Wettervorhersage der nächsten 24 Stunden von SRF Meteo.\n\n"
        "<use_case>Tagesplanung, Veranstaltungsorganisation, kurzfristige "
        "Wetterwarnungen.</use_case>\n\n"
        "<important_notes>Nur für Schweizer Standorte (Latitude 45.8–47.9, Longitude "
        "5.9–10.5). Liefert maximal 24 stündliche Datenpunkte.</important_notes>\n\n"
        "<example>latitude=47.3769, longitude=8.5417</example>"
    ),
    annotations={
        "title": "SRF Meteo – 24-Stunden-Prognose",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def srgssr_weather_forecast_24h(
    params: WeatherForecastInput,
    ctx: Context | None = None,
) -> WeatherForecast24hResponse | ToolErrorResponse:
    """Hourly 24-hour forecast for a Swiss location (SDK-002 strict model)."""
    log = logger.bind(
        tool="srgssr_weather_forecast_24h",
        latitude=params.latitude,
        longitude=params.longitude,
        geolocation_id=params.geolocation_id,
    )
    log.info("tool_invoked")
    if ctx is not None:
        await ctx.info(
            "srgssr_weather_forecast_24h invoked",
            latitude=params.latitude,
            longitude=params.longitude,
        )
    try:
        query_params: dict = {
            "latitude": params.latitude,
            "longitude": params.longitude,
        }
        if params.geolocation_id:
            query_params["geolocationId"] = params.geolocation_id
        data = await _api_get(f"{WEATHER_BASE}/24hour", params=query_params)
    except Exception as e:
        log.error("tool_failed", error_type=type(e).__name__, error=str(e))
        return _build_error_response(e)

    raw_hours = data.get("list", data.get("hour", [])) or []
    log.info("tool_succeeded", hours=len(raw_hours))

    hours: list[WeatherHour] = []
    for h in raw_hours[:24]:
        vals = h.get("values", {}) if isinstance(h, dict) else {}
        hours.append(
            WeatherHour(
                timestamp=str(h.get("dateTime", h.get("hour", "?"))),
                temperature_c=_extract_value(vals, "ttt"),
                precipitation_mm=_extract_value(vals, "rr"),
                weather_code=_extract_value(vals, "weatherCode"),
            )
        )

    return WeatherForecast24hResponse(
        latitude=params.latitude,
        longitude=params.longitude,
        geolocation_id=params.geolocation_id,
        hours=hours,
        count=len(hours),
    )


@mcp.tool(
    name="srgssr_weather_forecast_7day",
    description=(
        "Liefert die tägliche Wettervorhersage der nächsten 7 Tage von SRF Meteo "
        "mit Min/Max-Temperatur, Niederschlag und Wetterlage pro Tag.\n\n"
        "<use_case>Wochenplanung, Tourismus-Empfehlungen, Trendanalysen.</use_case>\n\n"
        "<important_notes>Nur für Schweizer Standorte. Liefert maximal 7 Tage; "
        "Tage 1–3 sind deutlich verlässlicher als Tage 5–7.</important_notes>\n\n"
        "<example>latitude=47.3769, longitude=8.5417</example>"
    ),
    annotations={
        "title": "SRF Meteo – 7-Tages-Prognose",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def srgssr_weather_forecast_7day(
    params: WeatherForecastInput,
    ctx: Context | None = None,
) -> WeatherForecast7dayResponse | ToolErrorResponse:
    """Daily 7-day forecast for a Swiss location (SDK-002 strict model)."""
    log = logger.bind(
        tool="srgssr_weather_forecast_7day",
        latitude=params.latitude,
        longitude=params.longitude,
        geolocation_id=params.geolocation_id,
    )
    log.info("tool_invoked")
    if ctx is not None:
        await ctx.info(
            "srgssr_weather_forecast_7day invoked",
            latitude=params.latitude,
            longitude=params.longitude,
        )
    try:
        query_params: dict = {
            "latitude": params.latitude,
            "longitude": params.longitude,
        }
        if params.geolocation_id:
            query_params["geolocationId"] = params.geolocation_id
        data = await _api_get(f"{WEATHER_BASE}/7day", params=query_params)
    except Exception as e:
        log.error("tool_failed", error_type=type(e).__name__, error=str(e))
        return _build_error_response(e)

    raw_days = data.get("list", data.get("day", [])) or []
    log.info("tool_succeeded", days=len(raw_days))

    days: list[WeatherDay] = []
    for d in raw_days[:7]:
        vals = d.get("values", {}) if isinstance(d, dict) else {}
        days.append(
            WeatherDay(
                date=str(d.get("dateTime", d.get("date", "?"))),
                temperature_min_c=_extract_value(vals, "ttn"),
                temperature_max_c=_extract_value(vals, "ttx"),
                precipitation_mm=_extract_value(vals, "rr"),
                weather_code=_extract_value(vals, "weatherCode"),
            )
        )

    return WeatherForecast7dayResponse(
        latitude=params.latitude,
        longitude=params.longitude,
        geolocation_id=params.geolocation_id,
        days=days,
        count=len(days),
    )
