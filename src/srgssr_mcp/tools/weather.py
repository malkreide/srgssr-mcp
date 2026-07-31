"""SRF Meteo tools: location search, current weather, 24h and 7-day forecasts."""

from mcp.server.mcpserver import Context
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
        description=(
            "Optionale geolocationId aus srgssr_weather_search_location. Ohne "
            "Angabe wird sie aus latitude/longitude aufgelöst."
        ),
        min_length=1,
        max_length=50,
        # SRF Meteo ids are either numeric or the documented '[lat],[lon]'
        # form, so dot and comma have to pass. '/' stays excluded, which is
        # what keeps the value from escaping its path segment.
        pattern=r"^[A-Za-z0-9_.,-]+$",
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
            # The v2 search takes `zip` for postal codes and `name` for
            # everything else; there is no combined search term.
            query_params = (
                {"zip": int(variant)} if variant.isdigit() else {"name": variant}
            )
            data = await _api_get(
                f"{WEATHER_BASE}/geolocationNames",
                params={**query_params, "limit": 10},
            )
            raw_locations = _as_location_list(data)
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

    locations = [_location_from_dict(loc) for loc in raw_locations]
    return WeatherLocationsResponse(
        query=params.query,
        matched_variant=matched_variant,
        tried=tried,
        locations=locations,
        count=len(locations),
    )


def _as_location_list(data) -> list:
    """Normalise the geolocationNames response to a list.

    The endpoint answers with a bare array for some queries and a single
    object for others, so both shapes are flattened here rather than at
    every call site.
    """
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if data.get("id") is not None:
            return [data]
        for key in ("geolocationNames", "geolocationList", "results"):
            value = data.get(key)
            if isinstance(value, list):
                return value
    return []


def _location_from_dict(d: dict) -> WeatherLocation:
    geo = d.get("geolocation") or {}
    plz = d.get("plz") or d.get("zip")
    return WeatherLocation(
        # The forecast endpoint keys off the geolocation id, not the name id.
        id=str(geo.get("id") or d.get("location_id") or d.get("id") or "?"),
        name=str(d.get("name") or d.get("default_name") or "Unbekannt"),
        canton=d.get("province") or d.get("district") or None,
        postalCode=str(plz) if plz is not None else None,
    )


def _forecast_point_id(latitude: float, longitude: float, explicit: str | None) -> str:
    """The path segment for /forecastpoint.

    Documented as ``'[lat],[lon]' rounded to 4 digits``. An explicit id from
    the search wins, because a named location resolves to a station the API
    actually has data for.
    """
    return explicit or f"{latitude:.4f},{longitude:.4f}"


async def _fetch_forecast_point(
    latitude: float, longitude: float, geolocation_id: str | None
) -> dict:
    """One call to /forecastpoint — it carries days, three_hours and hours.

    v2 has no separate current/24h/7day endpoints; the three tools slice
    different arrays out of this same payload.
    """
    point_id = _forecast_point_id(latitude, longitude, geolocation_id)
    return await _api_get(f"{WEATHER_BASE}/forecastpoint/{point_id}")


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
        data = await _fetch_forecast_point(
            params.latitude, params.longitude, params.geolocation_id
        )
    except Exception as e:
        log.error("tool_failed", error_type=type(e).__name__, error=str(e))
        return _build_error_response(e)

    log.info("tool_succeeded")

    # v2 has no "current" endpoint — the nearest hourly interval is it.
    hours = data.get("hours") or []
    now = hours[0] if hours else {}
    current = WeatherCurrent(
        temperature_c=now.get("TTT_C"),
        weather_code=now.get("symbol_code"),
        wind_speed_kmh=now.get("FF_KMH"),
        wind_direction_deg=now.get("DD_DEG"),
        precipitation_mm=now.get("RRR_MM"),
        relative_humidity_pct=now.get("RELHUM_PERCENT"),
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
        data = await _fetch_forecast_point(
            params.latitude, params.longitude, params.geolocation_id
        )
    except Exception as e:
        log.error("tool_failed", error_type=type(e).__name__, error=str(e))
        return _build_error_response(e)

    raw_hours = data.get("hours") or []
    log.info("tool_succeeded", hours=len(raw_hours))

    hours: list[WeatherHour] = [
        WeatherHour(
            timestamp=str(h.get("date_time", "?")),
            temperature_c=h.get("TTT_C"),
            precipitation_mm=h.get("RRR_MM"),
            weather_code=h.get("symbol_code"),
        )
        for h in raw_hours[:24]
    ]

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
        data = await _fetch_forecast_point(
            params.latitude, params.longitude, params.geolocation_id
        )
    except Exception as e:
        log.error("tool_failed", error_type=type(e).__name__, error=str(e))
        return _build_error_response(e)

    raw_days = data.get("days") or []
    log.info("tool_succeeded", days=len(raw_days))

    days: list[WeatherDay] = [
        WeatherDay(
            date=str(d.get("date_time", "?")),
            temperature_min_c=d.get("TN_C"),
            temperature_max_c=d.get("TX_C"),
            precipitation_mm=d.get("RRR_MM"),
            weather_code=d.get("symbol_code"),
        )
        for d in raw_days[:7]
    ]

    return WeatherForecast7dayResponse(
        latitude=params.latitude,
        longitude=params.longitude,
        geolocation_id=params.geolocation_id,
        days=days,
        count=len(days),
    )
