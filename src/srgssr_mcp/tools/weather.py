"""SRF Meteo tools: location search, current weather, 24h and 7-day forecasts."""

import json

from mcp.server.fastmcp import Context
from pydantic import BaseModel, ConfigDict, Field

from srgssr_mcp._app import ResponseFormat, mcp
from srgssr_mcp._http import WEATHER_BASE, _api_get, _handle_error, _query_variants
from srgssr_mcp._provenance import provenance_footer, with_provenance
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
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Ausgabeformat: 'markdown' oder 'json'",
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
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Ausgabeformat: 'markdown' oder 'json'",
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
        "gegenüber reinen Koordinaten. Bei mehrdeutigen Ortsnamen (z.B. mehrere "
        "'Buchs') werden mehrere Resultate zurückgegeben — der Aufrufer sollte "
        "nach Kanton oder PLZ disambiguieren.</important_notes>\n\n"
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
) -> str:
    """Sucht Schweizer Standorte für die Wettervorhersage nach Name oder Postleitzahl.
    Gibt eine Liste von Orten mit geolocationId zurück, die für Wetterabfragen benötigt wird.

    Args:
        params (WeatherSearchInput): Enthält:
            - query (str): Ortsname oder PLZ (z.B. 'Zürich', '8001')
            - response_format (str): 'markdown' oder 'json'
        ctx (Context, optional): FastMCP context for client-visible
            progress reports and per-call logging. Auto-injected when
            invoked through the MCP transport; ``None`` in unit tests.

    Returns:
        str: Liste von Standorten mit Name, Kanton, PLZ und geolocationId
    """
    log = logger.bind(tool="srgssr_weather_search_location", query=params.query)
    log.info("tool_invoked")
    if ctx is not None:
        await ctx.info(
            "srgssr_weather_search_location invoked", query=params.query
        )
    locations: list = []
    matched_variant = params.query
    tried: list[str] = []
    try:
        for variant in _query_variants(params.query):
            tried.append(variant)
            data = await _api_get(
                f"{WEATHER_BASE}/geolocations",
                params={"searchterm": variant},
            )
            locations = data.get("geolocationList", [])
            if locations:
                matched_variant = variant
                break
    except Exception as e:
        log.error("tool_failed", error_type=type(e).__name__, error=str(e), tried=tried)
        return _handle_error(e)

    log.info(
        "tool_succeeded",
        result_count=len(locations),
        matched_variant=matched_variant,
        variants_tried=len(tried),
    )

    if not locations:
        tried_str = ", ".join(f"'{t}'" for t in tried)
        return (
            f"Keine Standorte gefunden für: '{params.query}' "
            f"(versuchte Varianten: {tried_str}). "
            f"Vorschläge: deutsche Schreibweise mit Diakritika (z.B. 'Zürich', "
            f"'Genève', 'Bern'), die offizielle PLZ (z.B. '8001', '1003'), oder "
            f"einen kürzeren Namensbestandteil verwenden."
        )

    if params.response_format == ResponseFormat.JSON:
        return json.dumps(
            with_provenance(locations, list_key="locations"),
            indent=2,
            ensure_ascii=False,
        )

    header = f"## Gefundene Standorte für '{params.query}'"
    if matched_variant != params.query:
        header += f" (Treffer via '{matched_variant}')"
    lines = [header + "\n"]
    for loc in locations:
        lines.append(
            f"- **{loc.get('name', 'Unbekannt')}** "
            f"({loc.get('canton', '')}), PLZ {loc.get('postalCode', '-')} "
            f"— ID: `{loc.get('id', '')}`"
        )
    return "\n".join(lines) + provenance_footer()


@mcp.tool(
    name="srgssr_weather_current",
    description=(
        "Liefert die aktuelle Wettersituation von SRF Meteo für einen Schweizer Standort "
        "(Temperatur, Wettercode, Wind, Niederschlag, Luftfeuchtigkeit).\n\n"
        "<use_case>Echtzeit-Wetterabfragen für Outdoor-Aktivitäten, Verkehrsmeldungen, "
        "Energieprognosen oder kontextuelle Anreicherung von redaktionellen Inhalten. "
        "Wird verwendet, wenn der aktuelle Zustand wichtig ist; für stündliche "
        "Vorhersagen srgssr_weather_forecast_24h, für mehrtägige Trends "
        "srgssr_weather_forecast_7day verwenden.</use_case>\n\n"
        "<important_notes>Nur für Schweizer Standorte (Latitude 45.8–47.9, Longitude "
        "5.9–10.5). geolocation_id aus srgssr_weather_search_location erhöht die "
        "Genauigkeit gegenüber rohen Koordinaten und ist daher empfohlen. "
        "Wettercode entspricht der SRF-Meteo-Skala, nicht WMO.</important_notes>\n\n"
        "<example>latitude=47.3769, longitude=8.5417 (Zürich) | latitude=46.5197, "
        "longitude=6.6323, geolocation_id='100123' (Lausanne)</example>"
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
) -> str:
    """Liefert die aktuelle Wettervorhersage von SRF Meteo für einen Schweizer Standort.
    Nutzt Breitengrad, Längengrad und optional eine geolocationId.

    Args:
        params (WeatherForecastInput): Enthält:
            - latitude (float): Breitengrad (z.B. 47.3769)
            - longitude (float): Längengrad (z.B. 8.5417)
            - geolocation_id (Optional[str]): ID aus Standortsuche
            - response_format (str): 'markdown' oder 'json'
        ctx (Context, optional): FastMCP context for client-visible logging.

    Returns:
        str: Aktuelle Temperatur, Wetterlage, Wind, Niederschlag
    """
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
        query_params = {
            "latitude": params.latitude,
            "longitude": params.longitude,
        }
        if params.geolocation_id:
            query_params["geolocationId"] = params.geolocation_id
        data = await _api_get(f"{WEATHER_BASE}/current", params=query_params)
    except Exception as e:
        log.error("tool_failed", error_type=type(e).__name__, error=str(e))
        return _handle_error(e)

    log.info("tool_succeeded")

    if params.response_format == ResponseFormat.JSON:
        return json.dumps(with_provenance(data), indent=2, ensure_ascii=False)

    return _format_current_weather(data) + provenance_footer()


def _format_current_weather(data: dict) -> str:
    fc = data.get("currentForecast", data)
    lines = [
        "## Aktuelles Wetter (SRF Meteo)\n",
        f"**Temperatur:** {fc.get('values', {}).get('ttt', {}).get('value', '?')} °C",
        f"**Wettercode:** {fc.get('values', {}).get('weatherCode', {}).get('value', '?')}",
        f"**Wind:** {fc.get('values', {}).get('ff', {}).get('value', '?')} km/h, "
        f"Richtung {fc.get('values', {}).get('dd', {}).get('value', '?')}°",
        f"**Niederschlag (1h):** {fc.get('values', {}).get('rr', {}).get('value', '?')} mm",
        f"**Luftfeuchtigkeit:** {fc.get('values', {}).get('relhum', {}).get('value', '?')} %",
    ]
    return "\n".join(lines)


@mcp.tool(
    name="srgssr_weather_forecast_24h",
    description=(
        "Liefert die stündliche Wettervorhersage der nächsten 24 Stunden von SRF Meteo "
        "(Temperatur, Niederschlag, Wettercode pro Stunde).\n\n"
        "<use_case>Tagesplanung, Veranstaltungsorganisation, Reiseberichte oder "
        "kurzfristige Wetterwarnungen. Im Vergleich zu srgssr_weather_current die "
        "richtige Wahl, wenn der zeitliche Verlauf relevant ist; für Trends über "
        "mehrere Tage stattdessen srgssr_weather_forecast_7day verwenden.</use_case>\n\n"
        "<important_notes>Nur für Schweizer Standorte (Latitude 45.8–47.9, Longitude "
        "5.9–10.5). Liefert maximal 24 stündliche Datenpunkte ab dem nächsten "
        "Stundenschlag. geolocation_id aus srgssr_weather_search_location wird "
        "empfohlen für punktgenaue Vorhersagen.</important_notes>\n\n"
        "<example>latitude=47.3769, longitude=8.5417 | latitude=46.2044, "
        "longitude=6.1432, geolocation_id='100456'</example>"
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
) -> str:
    """Liefert die stündliche Wettervorhersage der nächsten 24 Stunden von SRF Meteo.

    Args:
        params (WeatherForecastInput): Standortangaben mit Koordinaten und optional geolocationId
        ctx (Context, optional): FastMCP context for client-visible logging.

    Returns:
        str: Stündliche Temperatur, Niederschlag, Wind für 24 Stunden
    """
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
        query_params = {
            "latitude": params.latitude,
            "longitude": params.longitude,
        }
        if params.geolocation_id:
            query_params["geolocationId"] = params.geolocation_id
        data = await _api_get(f"{WEATHER_BASE}/24hour", params=query_params)
    except Exception as e:
        log.error("tool_failed", error_type=type(e).__name__, error=str(e))
        return _handle_error(e)

    log.info("tool_succeeded", hours=len(data.get("list", data.get("hour", []))))

    if params.response_format == ResponseFormat.JSON:
        return json.dumps(with_provenance(data), indent=2, ensure_ascii=False)

    return _format_hourly_forecast(data) + provenance_footer()


def _format_hourly_forecast(data: dict) -> str:
    hours = data.get("list", data.get("hour", []))
    if not hours:
        return json.dumps(data, indent=2, ensure_ascii=False)
    lines = [
        "## 24-Stunden-Prognose (SRF Meteo)\n",
        "| Stunde | Temp °C | Niederschlag | Wetterlage |",
        "| --- | --- | --- | --- |",
    ]
    for h in hours[:24]:
        vals = h.get("values", {})
        lines.append(
            f"| {h.get('dateTime', h.get('hour', '?'))} "
            f"| {vals.get('ttt', {}).get('value', '?')} "
            f"| {vals.get('rr', {}).get('value', '?')} mm "
            f"| {vals.get('weatherCode', {}).get('value', '?')} |"
        )
    return "\n".join(lines)


@mcp.tool(
    name="srgssr_weather_forecast_7day",
    description=(
        "Liefert die tägliche Wettervorhersage der nächsten 7 Tage von SRF Meteo "
        "mit Min/Max-Temperatur, Niederschlag und Wetterlage pro Tag.\n\n"
        "<use_case>Wochenplanung, Tourismus-Empfehlungen, Trendanalysen oder "
        "Energie- und Landwirtschaftsprognosen. Im Unterschied zu "
        "srgssr_weather_forecast_24h die richtige Wahl, wenn ein mehrtägiger "
        "Überblick gefragt ist; für Echtzeit-Bedingungen srgssr_weather_current "
        "verwenden.</use_case>\n\n"
        "<important_notes>Nur für Schweizer Standorte (Latitude 45.8–47.9, Longitude "
        "5.9–10.5). Liefert maximal 7 Tage; die Vorhersagegüte nimmt mit der "
        "Distanz ab — Tage 1–3 sind deutlich verlässlicher als Tage 5–7. "
        "geolocation_id aus srgssr_weather_search_location empfohlen.</important_notes>\n\n"
        "<example>latitude=47.3769, longitude=8.5417 | latitude=46.0207, "
        "longitude=7.7491 (Zermatt)</example>"
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
) -> str:
    """Liefert die tägliche Wettervorhersage der nächsten 7 Tage von SRF Meteo.

    Args:
        params (WeatherForecastInput): Standortangaben mit Koordinaten und optional geolocationId
        ctx (Context, optional): FastMCP context for client-visible logging.

    Returns:
        str: Tagesvorhersage mit Min/Max-Temperatur, Niederschlag und Wetterlage
    """
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
        query_params = {
            "latitude": params.latitude,
            "longitude": params.longitude,
        }
        if params.geolocation_id:
            query_params["geolocationId"] = params.geolocation_id
        data = await _api_get(f"{WEATHER_BASE}/7day", params=query_params)
    except Exception as e:
        log.error("tool_failed", error_type=type(e).__name__, error=str(e))
        return _handle_error(e)

    log.info("tool_succeeded", days=len(data.get("list", data.get("day", []))))

    if params.response_format == ResponseFormat.JSON:
        return json.dumps(with_provenance(data), indent=2, ensure_ascii=False)

    return _format_7day_forecast(data) + provenance_footer()


def _format_7day_forecast(data: dict) -> str:
    days = data.get("list", data.get("day", []))
    if not days:
        return json.dumps(data, indent=2, ensure_ascii=False)
    lines = [
        "## 7-Tages-Prognose (SRF Meteo)\n",
        "| Datum | Min °C | Max °C | Niederschlag | Wetterlage |",
        "| --- | --- | --- | --- | --- |",
    ]
    for d in days[:7]:
        vals = d.get("values", {})
        lines.append(
            f"| {d.get('dateTime', d.get('date', '?'))} "
            f"| {vals.get('ttn', {}).get('value', '?')} "
            f"| {vals.get('ttx', {}).get('value', '?')} "
            f"| {vals.get('rr', {}).get('value', '?')} mm "
            f"| {vals.get('weatherCode', {}).get('value', '?')} |"
        )
    return "\n".join(lines)
