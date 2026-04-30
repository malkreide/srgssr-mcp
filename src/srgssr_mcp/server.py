"""
SRG SSR MCP Server
==================
Provides AI models with access to SRG SSR public APIs:
- SRF Weather (Swiss-wide forecasts)
- Video metadata (SRF, RTS, RSI, RTR, SWI)
- Audio metadata (radio shows and livestreams)
- EPG (Electronic Program Guide)
- Polis (Swiss votations and elections since 1900)

Authentication:
    Set SRGSSR_CONSUMER_KEY and SRGSSR_CONSUMER_SECRET as environment variables.
    Register at https://developer.srgssr.ch to obtain credentials.

Configuration is centralized in :class:`Settings` (Pydantic BaseSettings),
which also selects the MCP transport (``stdio``, ``sse``, ``streamable-http``)
via the ``SRGSSR_MCP_TRANSPORT`` environment variable.
"""

import base64
import json
import time
import unicodedata
from enum import StrEnum
from functools import lru_cache
from typing import Literal

import httpx
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL = "https://api.srgssr.ch"
TOKEN_URL = f"{BASE_URL}/oauth/v1/accesstoken"
WEATHER_BASE = f"{BASE_URL}/forecasts/v2.0/weather"
VIDEO_BASE = f"{BASE_URL}/video/v3"
AUDIO_BASE = f"{BASE_URL}/audio/v3"
EPG_BASE = f"{BASE_URL}/epg/v3"
POLIS_BASE = f"{BASE_URL}/polis/v1"

TIMEOUT = 30.0
USER_AGENT = "srgssr-mcp/1.0.0 (github.com/malkreide/srgssr-mcp)"

VALID_BU = ["srf", "rts", "rsi", "rtr", "swi"]

# ---------------------------------------------------------------------------
# Settings (Pydantic BaseSettings — single source of truth for configuration)
# ---------------------------------------------------------------------------

Transport = Literal["stdio", "sse", "streamable-http"]


class Settings(BaseSettings):
    """Centralized configuration loaded from environment variables.

    Environment variables (case-insensitive) with the ``SRGSSR_`` prefix map
    onto these fields. Credentials are required for any tool call that hits
    the SRG SSR API; the transport setting controls how :func:`main` runs the
    MCP server.
    """

    model_config = SettingsConfigDict(
        env_prefix="SRGSSR_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    consumer_key: str = Field(default="", validation_alias="SRGSSR_CONSUMER_KEY")
    consumer_secret: str = Field(default="", validation_alias="SRGSSR_CONSUMER_SECRET")

    transport: Transport = Field(
        default="stdio",
        validation_alias="SRGSSR_MCP_TRANSPORT",
        description="MCP transport: 'stdio' (local), 'sse' or 'streamable-http' (remote).",
    )
    host: str = Field(default="127.0.0.1", validation_alias="SRGSSR_MCP_HOST")
    port: int = Field(default=8000, validation_alias="SRGSSR_MCP_PORT")
    mount_path: str | None = Field(default=None, validation_alias="SRGSSR_MCP_MOUNT_PATH")

    def require_credentials(self) -> tuple[str, str]:
        if not self.consumer_key or not self.consumer_secret:
            raise ValueError(
                "SRGSSR_CONSUMER_KEY and SRGSSR_CONSUMER_SECRET must be set. "
                "Register at https://developer.srgssr.ch to obtain credentials."
            )
        return self.consumer_key, self.consumer_secret


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide :class:`Settings` instance (memoized)."""
    return Settings()


# ---------------------------------------------------------------------------
# Token management (simple in-memory cache)
# ---------------------------------------------------------------------------

_token_cache: dict = {"access_token": None, "expires_at": 0.0}


def _get_credentials() -> tuple[str, str]:
    return get_settings().require_credentials()


async def _get_access_token() -> str:
    """Returns a valid OAuth2 access token, refreshing if necessary."""
    now = time.time()
    if _token_cache["access_token"] and _token_cache["expires_at"] > now + 60:
        return _token_cache["access_token"]

    key, secret = _get_credentials()
    credentials = base64.b64encode(f"{key}:{secret}".encode()).decode()

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(
            TOKEN_URL,
            params={"grant_type": "client_credentials"},
            headers={
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": USER_AGENT,
            },
        )
        resp.raise_for_status()
        data = resp.json()

    _token_cache["access_token"] = data["access_token"]
    expires_in = int(data.get("expires_in", 3600))
    _token_cache["expires_at"] = now + expires_in
    return _token_cache["access_token"]


async def _api_get(url: str, params: dict | None = None) -> dict:
    """Authenticated GET helper returning parsed JSON."""
    token = await _get_access_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    }
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(url, params=params, headers=headers)
        resp.raise_for_status()
        return resp.json()


def _handle_error(e: Exception, not_found_hint: str | None = None) -> str:
    if isinstance(e, ValueError):
        return f"Konfigurationsfehler: {e}"
    if isinstance(e, httpx.HTTPStatusError):
        sc = e.response.status_code
        if sc == 401:
            return "Fehler 401: Ungültige API-Credentials. Bitte SRGSSR_CONSUMER_KEY und SRGSSR_CONSUMER_SECRET prüfen."
        if sc == 403:
            return (
                "Fehler 403: Zugriff verweigert. Möglicherweise fehlt der Zugriff"
                " auf diese API im gewählten Produkt."
            )
        if sc == 404:
            base = "Fehler 404: Ressource nicht gefunden. Bitte ID oder Parameter prüfen."
            return f"{base}\n\n**Tipp:** {not_found_hint}" if not_found_hint else base
        if sc == 429:
            return "Fehler 429: Rate-Limit überschritten. Bitte etwas warten und erneut versuchen."
        return f"API-Fehler {sc}: {e.response.text[:200]}"
    if isinstance(e, httpx.TimeoutException):
        return "Fehler: Anfrage hat das Timeout überschritten. Bitte erneut versuchen."
    return f"Unerwarteter Fehler ({type(e).__name__}): {e}"


def _query_variants(query: str) -> list[str]:
    """Returns deduplicated query variants for fuzzy retry.

    Generates the original query plus normalized forms (ASCII-folded for
    diacritic-insensitive matching, lowercased, title-cased) so that a search
    for "Zurich" still hits "Zürich" upstream and vice versa.
    """
    seen: set[str] = set()
    variants: list[str] = []
    folded = "".join(
        c for c in unicodedata.normalize("NFKD", query) if not unicodedata.combining(c)
    )
    for v in (query, folded, query.lower(), folded.lower(), query.title(), folded.title()):
        v = v.strip()
        if v and v not in seen:
            seen.add(v)
            variants.append(v)
    return variants


# ---------------------------------------------------------------------------
# Enums and shared models
# ---------------------------------------------------------------------------

class BusinessUnit(StrEnum):
    SRF = "srf"
    RTS = "rts"
    RSI = "rsi"
    RTR = "rtr"
    SWI = "swi"


class ResponseFormat(StrEnum):
    MARKDOWN = "markdown"
    JSON = "json"


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "srgssr_mcp",
    instructions=(
        "Provides access to SRG SSR public APIs covering Swiss weather, "
        "TV/radio metadata (SRF, RTS, RSI, RTR, SWI), program guides, and "
        "Swiss political data (votations and elections since 1900). "
        "All tools require valid SRGSSR_CONSUMER_KEY and SRGSSR_CONSUMER_SECRET."
    ),
)

# ===========================================================================
# WEATHER TOOLS
# ===========================================================================


class WeatherSearchInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    query: str = Field(
        ...,
        description="Ortname oder Postleitzahl in der Schweiz (z.B. 'Zürich', '8001', 'Luzern')",
        min_length=2,
        max_length=100,
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
async def srgssr_weather_search_location(params: WeatherSearchInput) -> str:
    """Sucht Schweizer Standorte für die Wettervorhersage nach Name oder Postleitzahl.
    Gibt eine Liste von Orten mit geolocationId zurück, die für Wetterabfragen benötigt wird.

    Args:
        params (WeatherSearchInput): Enthält:
            - query (str): Ortsname oder PLZ (z.B. 'Zürich', '8001')
            - response_format (str): 'markdown' oder 'json'

    Returns:
        str: Liste von Standorten mit Name, Kanton, PLZ und geolocationId
    """
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
        return _handle_error(e)

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
        return json.dumps(locations, indent=2, ensure_ascii=False)

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
    return "\n".join(lines)


class WeatherForecastInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
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
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Ausgabeformat: 'markdown' oder 'json'",
    )


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
async def srgssr_weather_current(params: WeatherForecastInput) -> str:
    """Liefert die aktuelle Wettervorhersage von SRF Meteo für einen Schweizer Standort.
    Nutzt Breitengrad, Längengrad und optional eine geolocationId.

    Args:
        params (WeatherForecastInput): Enthält:
            - latitude (float): Breitengrad (z.B. 47.3769)
            - longitude (float): Längengrad (z.B. 8.5417)
            - geolocation_id (Optional[str]): ID aus Standortsuche
            - response_format (str): 'markdown' oder 'json'

    Returns:
        str: Aktuelle Temperatur, Wetterlage, Wind, Niederschlag
    """
    try:
        query_params = {
            "latitude": params.latitude,
            "longitude": params.longitude,
        }
        if params.geolocation_id:
            query_params["geolocationId"] = params.geolocation_id
        data = await _api_get(f"{WEATHER_BASE}/current", params=query_params)
    except Exception as e:
        return _handle_error(e)

    if params.response_format == ResponseFormat.JSON:
        return json.dumps(data, indent=2, ensure_ascii=False)

    return _format_current_weather(data)


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
async def srgssr_weather_forecast_24h(params: WeatherForecastInput) -> str:
    """Liefert die stündliche Wettervorhersage der nächsten 24 Stunden von SRF Meteo.

    Args:
        params (WeatherForecastInput): Standortangaben mit Koordinaten und optional geolocationId

    Returns:
        str: Stündliche Temperatur, Niederschlag, Wind für 24 Stunden
    """
    try:
        query_params = {
            "latitude": params.latitude,
            "longitude": params.longitude,
        }
        if params.geolocation_id:
            query_params["geolocationId"] = params.geolocation_id
        data = await _api_get(f"{WEATHER_BASE}/24hour", params=query_params)
    except Exception as e:
        return _handle_error(e)

    if params.response_format == ResponseFormat.JSON:
        return json.dumps(data, indent=2, ensure_ascii=False)

    return _format_hourly_forecast(data)


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
async def srgssr_weather_forecast_7day(params: WeatherForecastInput) -> str:
    """Liefert die tägliche Wettervorhersage der nächsten 7 Tage von SRF Meteo.

    Args:
        params (WeatherForecastInput): Standortangaben mit Koordinaten und optional geolocationId

    Returns:
        str: Tagesvorhersage mit Min/Max-Temperatur, Niederschlag und Wetterlage
    """
    try:
        query_params = {
            "latitude": params.latitude,
            "longitude": params.longitude,
        }
        if params.geolocation_id:
            query_params["geolocationId"] = params.geolocation_id
        data = await _api_get(f"{WEATHER_BASE}/7day", params=query_params)
    except Exception as e:
        return _handle_error(e)

    if params.response_format == ResponseFormat.JSON:
        return json.dumps(data, indent=2, ensure_ascii=False)

    return _format_7day_forecast(data)


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


# ===========================================================================
# VIDEO TOOLS
# ===========================================================================


class VideoShowsInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    business_unit: BusinessUnit = Field(
        ...,
        description="SRG SSR Unternehmenseinheit: 'srf', 'rts', 'rsi', 'rtr' oder 'swi'",
    )
    page_size: int | None = Field(
        default=20,
        description="Anzahl Resultate pro Seite (1–100)",
        ge=1,
        le=100,
    )
    page: int | None = Field(
        default=1,
        description="Seitennummer für Paginierung",
        ge=1,
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Ausgabeformat: 'markdown' oder 'json'",
    )


@mcp.tool(
    name="srgssr_video_get_shows",
    description=(
        "Listet alle TV-Sendungen einer SRG SSR Unternehmenseinheit auf "
        "(SRF, RTS, RSI, RTR, SWI) mit Sendungstitel, ID und Beschreibung.\n\n"
        "<use_case>Katalog-Browsing für TV-Sendungen, Programmanalysen oder "
        "Recherche, welche Formate eine Sprachregion produziert. Erster Schritt, "
        "um eine show_id für srgssr_video_get_episodes zu ermitteln. Für "
        "Radiosendungen stattdessen srgssr_audio_get_shows verwenden, für "
        "Live-Sender srgssr_video_get_livestreams.</use_case>\n\n"
        "<important_notes>Liefert Sendungs-Metadaten, keine Episoden — Episodenliste "
        "erfordert einen separaten Aufruf von srgssr_video_get_episodes mit der "
        "show_id. Paginiert (page_size 1–100, Standard 20). Bei grossen Katalogen "
        "müssen mehrere Seiten abgerufen werden; das Tool zeigt einen Hinweis "
        "auf die nächste Seite an.</important_notes>\n\n"
        "<example>business_unit='srf' | business_unit='rts', page_size=50, "
        "page=2</example>"
    ),
    annotations={
        "title": "SRG SSR Video – Sendungen auflisten",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def srgssr_video_get_shows(params: VideoShowsInput) -> str:
    """Listet alle TV-Sendungen einer SRG SSR Unternehmenseinheit auf (SRF, RTS, RSI, RTR, SWI).
    Gibt Sendungstitel, ID und Beschreibung zurück.

    Args:
        params (VideoShowsInput): Enthält:
            - business_unit (str): 'srf', 'rts', 'rsi', 'rtr' oder 'swi'
            - page_size (int): Einträge pro Seite (Standard: 20)
            - page (int): Seitennummer
            - response_format (str): 'markdown' oder 'json'

    Returns:
        str: Liste von TV-Sendungen mit Titel, ID und Beschreibung
    """
    try:
        bu = params.business_unit.value
        data = await _api_get(
            f"{VIDEO_BASE}/{bu}/showList",
            params={"pageSize": params.page_size, "pageNumber": params.page},
        )
    except Exception as e:
        return _handle_error(e)

    shows = data.get("showList", data.get("shows", []))
    total = data.get("total", len(shows))

    if params.response_format == ResponseFormat.JSON:
        return json.dumps({"total": total, "shows": shows}, indent=2, ensure_ascii=False)

    bu_label = params.business_unit.value.upper()
    if not shows:
        return (
            f"Keine TV-Sendungen gefunden für business_unit='{bu}' "
            f"(Seite {params.page}). Vorschläge: andere Unternehmenseinheit "
            f"({', '.join(b for b in VALID_BU if b != bu)}) probieren, oder "
            f"page=1 setzen falls die Seitennummer zu hoch ist."
        )
    lines = [f"## TV-Sendungen – {bu_label} (Seite {params.page})\n", f"*Total: {total} Sendungen*\n"]
    for show in shows:
        title = show.get("title", show.get("name", "Unbekannt"))
        show_id = show.get("id", "?")
        description = show.get("description", show.get("lead", "")).strip()[:100]
        lines.append(f"- **{title}** (ID: `{show_id}`) — {description}")

    offset = (params.page - 1) * params.page_size + len(shows)
    if offset < total:
        lines.append(f"\n*Weitere Seiten verfügbar. Nächste Seite: page={params.page + 1}*")
    return "\n".join(lines)


class VideoEpisodesInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    business_unit: BusinessUnit = Field(
        ...,
        description="SRG SSR Unternehmenseinheit: 'srf', 'rts', 'rsi', 'rtr' oder 'swi'",
    )
    show_id: str = Field(
        ...,
        description="Sendungs-ID aus srgssr_video_get_shows (z.B. 'srf-tagesschau')",
        min_length=1,
        max_length=200,
    )
    page_size: int | None = Field(
        default=10,
        description="Anzahl Episoden pro Seite (1–50)",
        ge=1,
        le=50,
    )
    page: int | None = Field(
        default=1,
        description="Seitennummer",
        ge=1,
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Ausgabeformat: 'markdown' oder 'json'",
    )


@mcp.tool(
    name="srgssr_video_get_episodes",
    description=(
        "Ruft die neuesten Episoden einer TV-Sendung ab (Episodentitel, Datum, "
        "Dauer und Video-ID für den Mediaplayer Pillarbox).\n\n"
        "<use_case>Recherche zu konkreten Sendungsausgaben, Generierung von "
        "Programm-Übersichten, Auffinden archivierter Beiträge oder Verlinkung "
        "auf bestimmte Episoden. Setzt einen vorherigen Aufruf von "
        "srgssr_video_get_shows voraus, um die show_id zu ermitteln. Für ein "
        "tagesaktuelles TV-Programm stattdessen srgssr_epg_get_programs "
        "verwenden.</use_case>\n\n"
        "<important_notes>Liefert die jüngsten Episoden zuerst (chronologisch "
        "absteigend). Verfügbarkeit pro Episode kann durch Geo-Restriktionen "
        "und Lizenz-Embargos eingeschränkt sein. Paginiert mit page_size 1–50 "
        "(Standard 10). Episoden ohne Dauer-Feld werden mit '?' angezeigt.</important_notes>\n\n"
        "<example>business_unit='srf', show_id='srf-tagesschau' | "
        "business_unit='rts', show_id='rts-le-19h30', page_size=20</example>"
    ),
    annotations={
        "title": "SRG SSR Video – Episoden einer Sendung",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def srgssr_video_get_episodes(params: VideoEpisodesInput) -> str:
    """Ruft die neuesten Episoden einer TV-Sendung ab. Benötigt die show_id aus srgssr_video_get_shows.
    Gibt Episodentitel, Datum, Dauer und die Video-ID für den Mediaplayer zurück.

    Args:
        params (VideoEpisodesInput): Enthält:
            - business_unit (str): 'srf', 'rts', 'rsi', 'rtr' oder 'swi'
            - show_id (str): Sendungs-ID
            - page_size (int): Episoden pro Seite
            - page (int): Seitennummer
            - response_format (str): 'markdown' oder 'json'

    Returns:
        str: Episodenliste mit Titel, Datum, Dauer und Video-ID
    """
    try:
        bu = params.business_unit.value
        data = await _api_get(
            f"{VIDEO_BASE}/{bu}/showEpisodesList/{params.show_id}",
            params={"pageSize": params.page_size, "pageNumber": params.page},
        )
    except Exception as e:
        return _handle_error(
            e,
            not_found_hint=(
                f"Verwende srgssr_video_get_shows mit business_unit='{params.business_unit.value}', "
                f"um eine gültige show_id für '{params.show_id}' zu finden."
            ),
        )

    episodes = data.get("episodeList", data.get("medias", data.get("mediaList", [])))
    total = data.get("total", len(episodes))

    if params.response_format == ResponseFormat.JSON:
        return json.dumps({"total": total, "episodes": episodes}, indent=2, ensure_ascii=False)

    if not episodes:
        return (
            f"Keine Episoden gefunden für show_id='{params.show_id}' "
            f"({params.business_unit.value.upper()}). "
            f"Möglich: Sendung existiert ohne aktuelle Episoden, oder die show_id ist "
            f"ungültig. Vorschlag: srgssr_video_get_shows aufrufen, um die show_id zu "
            f"verifizieren."
        )

    lines = [f"## Episoden: {params.show_id} ({params.business_unit.value.upper()})\n"]
    for ep in episodes:
        title = ep.get("title", "Unbekannt")
        ep_id = ep.get("id", "?")
        date = ep.get("date", ep.get("publishedDate", "?"))
        duration = ep.get("duration", 0)
        dur_min = f"{duration // 60} min" if duration else "?"
        description = ep.get("description", ep.get("lead", "")).strip()[:120]
        lines.append(
            f"### {title}\n"
            f"- **Datum:** {date} | **Dauer:** {dur_min}\n"
            f"- **Video-ID:** `{ep_id}`\n"
            f"- {description}\n"
        )
    return "\n".join(lines)


class VideoLivestreamsInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    business_unit: BusinessUnit = Field(
        ...,
        description="SRG SSR Unternehmenseinheit: 'srf', 'rts', 'rsi', 'rtr' oder 'swi'",
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Ausgabeformat: 'markdown' oder 'json'",
    )


@mcp.tool(
    name="srgssr_video_get_livestreams",
    description=(
        "Listet alle Live-TV-Sender einer SRG SSR Unternehmenseinheit auf "
        "und liefert Sendernamen sowie Kanal-IDs für den Pillarbox-Mediaplayer.\n\n"
        "<use_case>Aufbau von Senderverzeichnissen, Live-Stream-Auswahl, "
        "Voraussetzung für srgssr_epg_get_programs (das eine channel_id "
        "benötigt) sowie für Mediaplayer-Integration. Für Radio-Live-Streams "
        "stattdessen srgssr_audio_get_livestreams verwenden, für aufgezeichnete "
        "Episoden srgssr_video_get_episodes.</use_case>\n\n"
        "<important_notes>Liefert nur Metadaten und IDs — keine Stream-URLs oder "
        "Player-Tokens. Anzahl Live-Kanäle variiert pro Unternehmenseinheit "
        "(SRF mehr Kanäle als RTR/SWI). Geografische Restriktionen können beim "
        "tatsächlichen Streaming greifen.</important_notes>\n\n"
        "<example>business_unit='srf' | business_unit='rsi'</example>"
    ),
    annotations={
        "title": "SRG SSR Video – Live-TV-Sender",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def srgssr_video_get_livestreams(params: VideoLivestreamsInput) -> str:
    """Listet alle Live-TV-Sender einer SRG SSR Unternehmenseinheit auf.
    Gibt Sendernamen und Kanal-IDs zurück, die mit dem SRG-Mediaplayer (Pillarbox) genutzt werden können.

    Args:
        params (VideoLivestreamsInput): Enthält:
            - business_unit (str): 'srf', 'rts', 'rsi', 'rtr' oder 'swi'
            - response_format (str): 'markdown' oder 'json'

    Returns:
        str: Liste der Live-TV-Sender mit Name und Kanal-ID
    """
    try:
        bu = params.business_unit.value
        data = await _api_get(f"{VIDEO_BASE}/{bu}/channels")
    except Exception as e:
        return _handle_error(e)

    channels = data.get("channelList", data.get("channels", []))

    if params.response_format == ResponseFormat.JSON:
        return json.dumps(channels, indent=2, ensure_ascii=False)

    bu_label = params.business_unit.value.upper()
    if not channels:
        return (
            f"Keine Live-TV-Sender für business_unit='{params.business_unit.value}' "
            f"verfügbar. RTR und SWI haben weniger oder keine Live-Kanäle; eine "
            f"andere Unternehmenseinheit ({', '.join(b for b in VALID_BU if b != params.business_unit.value)}) "
            f"liefert in der Regel mehr Resultate."
        )
    lines = [f"## Live-TV-Sender – {bu_label}\n"]
    for ch in channels:
        name = ch.get("title", ch.get("name", "Unbekannt"))
        ch_id = ch.get("id", "?")
        lines.append(f"- **{name}** — ID: `{ch_id}`")
    return "\n".join(lines)


# ===========================================================================
# AUDIO TOOLS
# ===========================================================================


@mcp.tool(
    name="srgssr_audio_get_shows",
    description=(
        "Listet alle Radiosendungen einer SRG SSR Unternehmenseinheit auf "
        "(SRF, RTS, RSI, RTR, SWI) mit Sendungstitel, ID und Beschreibung.\n\n"
        "<use_case>Katalog-Browsing für Radio- und Podcast-Formate, Recherche zu "
        "Audio-Inhalten in allen vier Landessprachen, Voraussetzung um eine "
        "show_id für srgssr_audio_get_episodes zu ermitteln. Für TV-Sendungen "
        "stattdessen srgssr_video_get_shows verwenden, für Live-Radio-Sender "
        "srgssr_audio_get_livestreams.</use_case>\n\n"
        "<important_notes>Liefert ausschliesslich Sendungs-Metadaten — Episodenliste "
        "über srgssr_audio_get_episodes mit der show_id. Paginiert (page_size "
        "1–100, Standard 20). Audio-Kataloge enthalten häufig auch reine Podcasts "
        "ohne On-Air-Ausstrahlung.</important_notes>\n\n"
        "<example>business_unit='srf' | business_unit='rsi', page_size=50</example>"
    ),
    annotations={
        "title": "SRG SSR Audio – Radiosendungen auflisten",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def srgssr_audio_get_shows(params: VideoShowsInput) -> str:
    """Listet alle Radiosendungen einer SRG SSR Unternehmenseinheit auf (SRF, RTS, RSI, RTR, SWI).
    Gibt Sendungstitel, ID und Beschreibung zurück.

    Args:
        params (VideoShowsInput): Enthält:
            - business_unit (str): 'srf', 'rts', 'rsi', 'rtr' oder 'swi'
            - page_size (int): Einträge pro Seite (Standard: 20)
            - page (int): Seitennummer
            - response_format (str): 'markdown' oder 'json'

    Returns:
        str: Liste von Radiosendungen mit Titel, ID und Beschreibung
    """
    try:
        bu = params.business_unit.value
        data = await _api_get(
            f"{AUDIO_BASE}/{bu}/showList",
            params={"pageSize": params.page_size, "pageNumber": params.page},
        )
    except Exception as e:
        return _handle_error(e)

    shows = data.get("showList", data.get("shows", []))
    total = data.get("total", len(shows))

    if params.response_format == ResponseFormat.JSON:
        return json.dumps({"total": total, "shows": shows}, indent=2, ensure_ascii=False)

    bu_label = params.business_unit.value.upper()
    if not shows:
        return (
            f"Keine Radiosendungen gefunden für business_unit='{bu}' "
            f"(Seite {params.page}). Vorschläge: andere Unternehmenseinheit "
            f"({', '.join(b for b in VALID_BU if b != bu)}) probieren, oder "
            f"page=1 setzen falls die Seitennummer zu hoch ist."
        )
    lines = [f"## Radiosendungen – {bu_label} (Seite {params.page})\n", f"*Total: {total} Sendungen*\n"]
    for show in shows:
        title = show.get("title", show.get("name", "Unbekannt"))
        show_id = show.get("id", "?")
        description = show.get("description", show.get("lead", "")).strip()[:100]
        lines.append(f"- **{title}** (ID: `{show_id}`) — {description}")

    offset = (params.page - 1) * params.page_size + len(shows)
    if offset < total:
        lines.append(f"\n*Weitere Seiten verfügbar. Nächste Seite: page={params.page + 1}*")
    return "\n".join(lines)


class AudioEpisodesInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    business_unit: BusinessUnit = Field(
        ...,
        description="SRG SSR Unternehmenseinheit: 'srf', 'rts', 'rsi', 'rtr' oder 'swi'",
    )
    show_id: str = Field(
        ...,
        description="Sendungs-ID aus srgssr_audio_get_shows",
        min_length=1,
        max_length=200,
    )
    page_size: int | None = Field(default=10, ge=1, le=50, description="Episoden pro Seite")
    page: int | None = Field(default=1, ge=1, description="Seitennummer")
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Ausgabeformat: 'markdown' oder 'json'",
    )


@mcp.tool(
    name="srgssr_audio_get_episodes",
    description=(
        "Ruft die neuesten Episoden einer Radiosendung ab (Episodentitel, Datum, "
        "Dauer und Audio-ID für den SRG-Mediaplayer).\n\n"
        "<use_case>Auffinden konkreter Radiobeiträge oder Podcast-Folgen, "
        "Generierung von Audio-Listen, Verlinkung auf Beiträge in Artikeln. "
        "Setzt einen vorherigen Aufruf von srgssr_audio_get_shows voraus, um "
        "die show_id zu erhalten. Für TV-Episoden srgssr_video_get_episodes, "
        "für Live-Radio srgssr_audio_get_livestreams verwenden.</use_case>\n\n"
        "<important_notes>Liefert Episoden in chronologisch absteigender Reihenfolge "
        "(neueste zuerst). Paginiert mit page_size 1–50 (Standard 10). Lizenz- "
        "und Geo-Restriktionen können einzelne Episoden beim tatsächlichen "
        "Abspielen sperren — die Audio-ID ist trotzdem verfügbar.</important_notes>\n\n"
        "<example>business_unit='srf', show_id='echo' | business_unit='rts', "
        "show_id='rts-tribu', page_size=20</example>"
    ),
    annotations={
        "title": "SRG SSR Audio – Episoden einer Sendung",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def srgssr_audio_get_episodes(params: AudioEpisodesInput) -> str:
    """Ruft die neuesten Episoden einer Radiosendung ab. Benötigt die show_id aus srgssr_audio_get_shows.
    Gibt Episodentitel, Datum, Dauer und die Audio-ID für den Mediaplayer zurück.

    Args:
        params (AudioEpisodesInput): Enthält:
            - business_unit (str): 'srf', 'rts', 'rsi', 'rtr' oder 'swi'
            - show_id (str): Sendungs-ID
            - page_size (int): Episoden pro Seite
            - page (int): Seitennummer
            - response_format (str): 'markdown' oder 'json'

    Returns:
        str: Episodenliste mit Titel, Datum, Dauer und Audio-ID
    """
    try:
        bu = params.business_unit.value
        data = await _api_get(
            f"{AUDIO_BASE}/{bu}/showEpisodesList/{params.show_id}",
            params={"pageSize": params.page_size, "pageNumber": params.page},
        )
    except Exception as e:
        return _handle_error(
            e,
            not_found_hint=(
                f"Verwende srgssr_audio_get_shows mit business_unit='{params.business_unit.value}', "
                f"um eine gültige show_id für '{params.show_id}' zu finden."
            ),
        )

    episodes = data.get("episodeList", data.get("medias", []))
    total = data.get("total", len(episodes))

    if params.response_format == ResponseFormat.JSON:
        return json.dumps({"total": total, "episodes": episodes}, indent=2, ensure_ascii=False)

    if not episodes:
        return (
            f"Keine Audio-Episoden gefunden für show_id='{params.show_id}' "
            f"({params.business_unit.value.upper()}). "
            f"Möglich: Sendung existiert ohne aktuelle Episoden, oder die show_id ist "
            f"ungültig. Vorschlag: srgssr_audio_get_shows aufrufen, um die show_id zu "
            f"verifizieren."
        )

    lines = [f"## Audio-Episoden: {params.show_id} ({params.business_unit.value.upper()})\n"]
    for ep in episodes:
        title = ep.get("title", "Unbekannt")
        ep_id = ep.get("id", "?")
        date = ep.get("date", ep.get("publishedDate", "?"))
        duration = ep.get("duration", 0)
        dur_min = f"{duration // 60} min" if duration else "?"
        description = ep.get("description", ep.get("lead", "")).strip()[:120]
        lines.append(
            f"### {title}\n"
            f"- **Datum:** {date} | **Dauer:** {dur_min}\n"
            f"- **Audio-ID:** `{ep_id}`\n"
            f"- {description}\n"
        )
    return "\n".join(lines)


@mcp.tool(
    name="srgssr_audio_get_livestreams",
    description=(
        "Listet alle Live-Radiosender einer SRG SSR Unternehmenseinheit auf "
        "und liefert Sendernamen sowie Kanal-IDs für den SRG-Mediaplayer.\n\n"
        "<use_case>Aufbau von Radio-Senderverzeichnissen, Live-Stream-Auswahl, "
        "Voraussetzung für srgssr_epg_get_programs (das eine channel_id "
        "benötigt). Für Live-TV stattdessen srgssr_video_get_livestreams "
        "verwenden, für aufgezeichnete Episoden srgssr_audio_get_episodes.</use_case>\n\n"
        "<important_notes>Liefert nur Metadaten und IDs — keine Stream-URLs. "
        "Die Anzahl Live-Kanäle variiert pro Unternehmenseinheit (SRF mit "
        "mehreren Programmen, SWI mit weniger). Geo-Restriktionen können beim "
        "tatsächlichen Streaming greifen.</important_notes>\n\n"
        "<example>business_unit='srf' | business_unit='rts'</example>"
    ),
    annotations={
        "title": "SRG SSR Audio – Live-Radiosender",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def srgssr_audio_get_livestreams(params: VideoLivestreamsInput) -> str:
    """Listet alle Live-Radiosender einer SRG SSR Unternehmenseinheit auf.
    Gibt Sendernamen und Kanal-IDs zurück, die mit dem SRG-Mediaplayer (Letterbox) genutzt werden können.

    Args:
        params (VideoLivestreamsInput): Enthält:
            - business_unit (str): 'srf', 'rts', 'rsi', 'rtr' oder 'swi'
            - response_format (str): 'markdown' oder 'json'

    Returns:
        str: Liste der Live-Radiosender mit Name und Kanal-ID
    """
    try:
        bu = params.business_unit.value
        data = await _api_get(f"{AUDIO_BASE}/{bu}/channels")
    except Exception as e:
        return _handle_error(e)

    channels = data.get("channelList", data.get("channels", []))

    if params.response_format == ResponseFormat.JSON:
        return json.dumps(channels, indent=2, ensure_ascii=False)

    bu_label = params.business_unit.value.upper()
    if not channels:
        return (
            f"## Live-Radiosender – {bu_label}\n\n"
            f"Keine Live-Radiosender für business_unit='{params.business_unit.value}' "
            f"verfügbar. Eine andere Unternehmenseinheit "
            f"({', '.join(b for b in VALID_BU if b != params.business_unit.value)}) "
            f"liefert in der Regel mehr Resultate."
        )
    lines = [f"## Live-Radiosender – {bu_label}\n"]
    for ch in channels:
        name = ch.get("title", ch.get("name", "Unbekannt"))
        ch_id = ch.get("id", "?")
        lines.append(f"- **{name}** — ID: `{ch_id}`")
    return "\n".join(lines)


# ===========================================================================
# EPG TOOLS
# ===========================================================================


class EpgProgramsInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    business_unit: BusinessUnit = Field(
        ...,
        description="SRG SSR Unternehmenseinheit: 'srf', 'rts', 'rsi' (EPG für RTR/SWI nicht verfügbar)",
    )
    channel_id: str = Field(
        ...,
        description="Kanal-ID aus srgssr_video_get_livestreams (z.B. 'srf1', 'rts1', 'rsi-la1')",
        min_length=1,
        max_length=100,
    )
    date: str = Field(
        ...,
        description="Datum im Format YYYY-MM-DD (z.B. '2025-03-08')",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Ausgabeformat: 'markdown' oder 'json'",
    )


@mcp.tool(
    name="srgssr_epg_get_programs",
    description=(
        "Ruft den vollständigen Programmplan (Electronic Program Guide) eines "
        "SRG SSR TV- oder Radiosenders für einen bestimmten Tag ab "
        "(Startzeit, Titel, Untertitel, Beschreibung).\n\n"
        "<use_case>TV-/Radio-Programmvorschauen, redaktionelle Programm-Tipps, "
        "Recherche zu historischen Sendeplätzen, Zuschauer-Empfehlungen oder "
        "Aufbau von Programm-Apps. Im Unterschied zu srgssr_video_get_episodes "
        "(Episoden einer einzelnen Sendung) liefert dieses Tool das gesamte "
        "Tagesprogramm eines Kanals chronologisch.</use_case>\n\n"
        "<important_notes>Verfügbar nur für SRF, RTS und RSI — nicht für RTR "
        "oder SWI. channel_id muss aus srgssr_video_get_livestreams oder "
        "srgssr_audio_get_livestreams stammen (z.B. 'srf1', 'rts1', 'rsi-la1'). "
        "Datum strikt im Format YYYY-MM-DD. Programmänderungen kurzfristig "
        "möglich; das EPG kann von der tatsächlichen Ausstrahlung abweichen.</important_notes>\n\n"
        "<example>business_unit='srf', channel_id='srf1', date='2026-04-30' | "
        "business_unit='rts', channel_id='rts1', date='2026-05-01'</example>"
    ),
    annotations={
        "title": "SRG SSR EPG – Programmvorschau",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def srgssr_epg_get_programs(params: EpgProgramsInput) -> str:
    """Ruft den Programmplan (Electronic Program Guide) für einen SRG SSR TV- oder Radiosender ab.
    Gibt alle Sendungen für einen bestimmten Tag zurück (Startzeit, Titel, Beschreibung).
    Unterstützt: SRF, RTS, RSI.

    Args:
        params (EpgProgramsInput): Enthält:
            - business_unit (str): 'srf', 'rts' oder 'rsi'
            - channel_id (str): Kanal-ID (z.B. 'srf1', 'rts1')
            - date (str): Datum YYYY-MM-DD
            - response_format (str): 'markdown' oder 'json'

    Returns:
        str: Programmliste des Tages mit Startuhrzeit, Titel und Beschreibung
    """
    try:
        bu = params.business_unit.value
        data = await _api_get(
            f"{EPG_BASE}/programs",
            params={"bu": bu, "channel": params.channel_id, "date": params.date},
        )
    except Exception as e:
        return _handle_error(
            e,
            not_found_hint=(
                f"channel_id='{params.channel_id}' nicht gefunden für "
                f"business_unit='{params.business_unit.value}'. Verwende "
                f"srgssr_video_get_livestreams oder srgssr_audio_get_livestreams, "
                f"um eine gültige channel_id zu finden. EPG ist nur für SRF, RTS "
                f"und RSI verfügbar."
            ),
        )

    programs = data.get("programList", data.get("programs", []))

    if params.response_format == ResponseFormat.JSON:
        return json.dumps(programs, indent=2, ensure_ascii=False)

    if not programs:
        return (
            f"Keine Programmeinträge für channel_id='{params.channel_id}' "
            f"({params.business_unit.value.upper()}) am {params.date}. "
            f"Vorschläge: Datum prüfen (Format YYYY-MM-DD, sehr ferne Zukunft "
            f"oft nicht verfügbar), oder channel_id über "
            f"srgssr_video_get_livestreams verifizieren."
        )

    lines = [
        f"## Programm – {params.channel_id.upper()} ({params.business_unit.value.upper()}) "
        f"am {params.date}\n"
    ]
    for prog in programs:
        start = prog.get("startTime", prog.get("date", "?"))
        title = prog.get("title", "Unbekannt")
        subtitle = prog.get("subtitle", "")
        description = prog.get("description", prog.get("lead", "")).strip()[:100]
        lines.append(
            f"**{start}** — {title}"
            + (f": {subtitle}" if subtitle else "")
            + (f"\n  {description}" if description else "")
        )
    return "\n".join(lines)


# ===========================================================================
# POLIS TOOLS
# ===========================================================================


class PolisListInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    year_from: int | None = Field(
        default=None,
        description="Startjahr der Abfrage (z.B. 2000). Minimum: 1900",
        ge=1900,
        le=2100,
    )
    year_to: int | None = Field(
        default=None,
        description="Endjahr der Abfrage (z.B. 2024)",
        ge=1900,
        le=2100,
    )
    canton: str | None = Field(
        default=None,
        description=(
            "Kantonskürzel für kantonale Abstimmungen (z.B. 'ZH', 'BE', 'GE')."
            " Leer für nationale Abstimmungen."
        ),
        max_length=4,
    )
    page_size: int | None = Field(default=20, ge=1, le=100, description="Einträge pro Seite")
    page: int | None = Field(default=1, ge=1, description="Seitennummer")
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Ausgabeformat: 'markdown' oder 'json'",
    )


@mcp.tool(
    name="srgssr_polis_get_votations",
    description=(
        "Ruft Schweizer Volksabstimmungen und Referenden (national und kantonal) "
        "aus dem Polis-System ab. Liefert Datum, Titel und votation_id pro Eintrag.\n\n"
        "<use_case>Historische Analysen von Abstimmungsverhalten, journalistische "
        "Recherchen zu direkter Demokratie, Bildungszwecke für Schweizer Politik, "
        "Trendanalysen über Kantone und Zeiträume. Erster Schritt, um eine "
        "votation_id für srgssr_polis_get_votation_results zu ermitteln. Für "
        "Wahlen (Nationalrat, Ständerat) stattdessen "
        "srgssr_polis_get_elections.</use_case>\n\n"
        "<important_notes>Daten reichen zurück bis 1900. Filter nach Jahr "
        "(year_from/year_to, beide 1900–2100) und Kanton möglich. Ohne canton-Filter "
        "werden nationale Abstimmungen geliefert; mit Kantonskürzel ('ZH', 'BE', "
        "'GE' …) kantonale. Liefert nur Metadaten — detaillierte Resultate "
        "(Ja/Nein-Anteile, Stimmbeteiligung) über srgssr_polis_get_votation_results. "
        "Paginiert mit page_size 1–100.</important_notes>\n\n"
        "<example>year_from=2020, year_to=2024 | canton='ZH', year_from=2000 | "
        "page_size=50, page=1</example>"
    ),
    annotations={
        "title": "SRG SSR Polis – Schweizer Abstimmungen",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def srgssr_polis_get_votations(params: PolisListInput) -> str:
    """Ruft Schweizer Volksabstimmungen und Referenden aus dem Polis-System ab.
    Daten reichen zurück bis 1900. Kann nach Jahr und Kanton gefiltert werden.
    Ideal für historische Analysen, Bildungszwecke und journalistische Recherchen.

    Args:
        params (PolisListInput): Enthält:
            - year_from (Optional[int]): Startjahr (Standard: alle)
            - year_to (Optional[int]): Endjahr (Standard: alle)
            - canton (Optional[str]): Kantonskürzel (z.B. 'ZH') oder leer für national
            - page_size (int): Einträge pro Seite
            - page (int): Seitennummer
            - response_format (str): 'markdown' oder 'json'

    Returns:
        str: Liste von Abstimmungen mit Datum, Titel und Abstimmungs-ID
    """
    try:
        query_params: dict = {
            "pageSize": params.page_size,
            "pageNumber": params.page,
        }
        if params.year_from:
            query_params["yearFrom"] = params.year_from
        if params.year_to:
            query_params["yearTo"] = params.year_to
        if params.canton:
            query_params["canton"] = params.canton.upper()

        data = await _api_get(f"{POLIS_BASE}/votations", params=query_params)
    except Exception as e:
        return _handle_error(e)

    votations = data.get("votationList", data.get("votations", []))
    total = data.get("total", len(votations))

    if params.response_format == ResponseFormat.JSON:
        return json.dumps({"total": total, "votations": votations}, indent=2, ensure_ascii=False)

    filter_desc = []
    if params.year_from or params.year_to:
        filter_desc.append(f"Jahre {params.year_from or '1900'}–{params.year_to or 'heute'}")
    if params.canton:
        filter_desc.append(f"Kanton {params.canton.upper()}")
    filter_str = " | ".join(filter_desc) if filter_desc else "alle"

    if not votations:
        suggestions = []
        if params.canton:
            suggestions.append(
                f"canton-Filter entfernen (kantonale Abstimmungen für "
                f"'{params.canton.upper()}' sind möglicherweise nicht erfasst)"
            )
        if params.year_from and params.year_from > 1990:
            suggestions.append(f"year_from auf einen früheren Wert setzen (z.B. {params.year_from - 10})")
        if params.year_to and params.year_to < 2024:
            suggestions.append(f"year_to auf einen späteren Wert setzen (z.B. {params.year_to + 10})")
        if not suggestions:
            suggestions.append("Filter weglassen, um den vollen Datenbestand seit 1900 zu sehen")
        return (
            f"Keine Volksabstimmungen gefunden ({filter_str}). "
            f"Vorschläge: " + "; ".join(suggestions) + "."
        )

    lines = [
        f"## Schweizer Volksabstimmungen ({filter_str})\n",
        f"*Total: {total} Abstimmungen, Seite {params.page}*\n",
    ]
    for v in votations:
        v_date = v.get("date", v.get("votationDate", "?"))
        title = v.get("title", v.get("titleDe", "Unbekannt"))
        v_id = v.get("id", "?")
        lines.append(f"- **{v_date}** — {title} (ID: `{v_id}`)")

    return "\n".join(lines)


class PolisResultInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    votation_id: str = Field(
        ...,
        description="Abstimmungs-ID aus srgssr_polis_get_votations",
        min_length=1,
        max_length=100,
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Ausgabeformat: 'markdown' oder 'json'",
    )


@mcp.tool(
    name="srgssr_polis_get_votation_results",
    description=(
        "Ruft detaillierte Resultate einer einzelnen Schweizer Volksabstimmung ab "
        "(Ja/Nein-Anteile, Stimmbeteiligung, kantonale Ergebnisse, "
        "Annahme/Ablehnung).\n\n"
        "<use_case>Vertiefte politische Analysen, Visualisierung kantonaler "
        "Unterschiede, redaktionelle Aufbereitung von Abstimmungs-Sonntagen, "
        "Vergleiche zwischen Sprachregionen oder Stadt/Land. Im Unterschied zu "
        "srgssr_polis_get_votations (Liste mit Metadaten) liefert dieses Tool "
        "die vollständigen Resultate einer einzelnen Abstimmung.</use_case>\n\n"
        "<important_notes>Erfordert eine votation_id, die zuvor über "
        "srgssr_polis_get_votations ermittelt wurde. Bei sehr aktuellen "
        "Abstimmungen kann das Resultat-Feld leer sein ('Ergebnis ausstehend'). "
        "Kantonale Resultate werden nur für nationale Abstimmungen mit "
        "Ständemehr-Erfordernis vollständig geliefert.</important_notes>\n\n"
        "<example>votation_id='v1' | votation_id='2024-09-22-bildung'</example>"
    ),
    annotations={
        "title": "SRG SSR Polis – Abstimmungsresultate",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def srgssr_polis_get_votation_results(params: PolisResultInput) -> str:
    """Ruft detaillierte Resultate einer Schweizer Volksabstimmung ab.
    Liefert Ja/Nein-Anteile, Stimmbeteiligung und kantonale Ergebnisse.
    Benötigt eine votation_id aus srgssr_polis_get_votations.

    Args:
        params (PolisResultInput): Enthält:
            - votation_id (str): Abstimmungs-ID
            - response_format (str): 'markdown' oder 'json'

    Returns:
        str: Detaillierte Abstimmungsresultate mit Ja/Nein-Anteilen und kantonalen Ergebnissen
    """
    try:
        data = await _api_get(f"{POLIS_BASE}/votations/{params.votation_id}")
    except Exception as e:
        return _handle_error(
            e,
            not_found_hint=(
                f"votation_id='{params.votation_id}' nicht gefunden. Verwende "
                f"srgssr_polis_get_votations (optional mit year_from/year_to oder "
                f"canton) und übernimm die ID aus der Resultatliste."
            ),
        )

    if params.response_format == ResponseFormat.JSON:
        return json.dumps(data, indent=2, ensure_ascii=False)

    return _format_votation_result(data)


def _format_votation_result(data: dict) -> str:
    title = data.get("title", data.get("titleDe", "Abstimmung"))
    v_date = data.get("date", data.get("votationDate", "?"))
    result = data.get("result", {})

    yes_pct = result.get("yesPercentage", result.get("jaStimmenInProzent", "?"))
    no_pct = result.get("noPercentage", result.get("neinStimmenInProzent", "?"))
    accepted = result.get("accepted", result.get("angenommen", None))
    turnout = result.get("turnout", result.get("stimmbeteiligung", "?"))

    accepted_label = "✅ Angenommen" if accepted else ("❌ Abgelehnt" if accepted is False else "Ergebnis ausstehend")

    lines = [
        f"## {title}\n",
        f"**Datum:** {v_date}",
        f"**Resultat:** {accepted_label}",
        f"**Ja:** {yes_pct}% | **Nein:** {no_pct}%",
        f"**Stimmbeteiligung:** {turnout}%",
    ]

    cantonal = data.get("cantonalResults", data.get("kantonaleResultate", []))
    if cantonal:
        lines.append("\n### Kantonale Resultate")
        for cr in cantonal:
            kanton = cr.get("canton", cr.get("kanton", "?"))
            k_yes = cr.get("yesPercentage", cr.get("jaStimmenInProzent", "?"))
            k_accepted = "✅" if cr.get("accepted", cr.get("angenommen", False)) else "❌"
            lines.append(f"- {k_accepted} **{kanton}**: {k_yes}% Ja")

    return "\n".join(lines)


@mcp.tool(
    name="srgssr_polis_get_elections",
    description=(
        "Ruft Schweizer Nationalrats-, Ständerats- und kantonale Regierungs- bzw. "
        "Parlamentswahlen aus dem Polis-System ab. Liefert Datum, Wahlbezeichnung "
        "und Wahl-ID pro Eintrag.\n\n"
        "<use_case>Historische Wahlanalysen, journalistische Recherchen zu "
        "politischen Mehrheiten, Bildungsmaterial zum Schweizer Wahlsystem, "
        "Trendvergleiche zwischen Wahljahren. Im Unterschied zu "
        "srgssr_polis_get_votations (Sachvorlagen) liefert dieses Tool "
        "Personenwahlen.</use_case>\n\n"
        "<important_notes>Daten reichen zurück bis 1900. Filter nach Jahr "
        "(year_from/year_to) und Kanton möglich; ohne canton-Filter werden "
        "nationale Wahlen geliefert. Liefert ausschliesslich Wahl-Metadaten "
        "(keine Stimmen-Resultate oder Sitzverteilungen). Paginiert mit "
        "page_size 1–100.</important_notes>\n\n"
        "<example>year_from=2023 | canton='ZH', year_from=2015, year_to=2024 | "
        "page_size=50</example>"
    ),
    annotations={
        "title": "SRG SSR Polis – Schweizer Wahlen",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def srgssr_polis_get_elections(params: PolisListInput) -> str:
    """Ruft Schweizer Nationalrats- und Ständeratswahlen sowie Regierungsratswahlen aus dem Polis-System ab.
    Daten reichen zurück bis 1900.

    Args:
        params (PolisListInput): Enthält:
            - year_from (Optional[int]): Startjahr
            - year_to (Optional[int]): Endjahr
            - canton (Optional[str]): Kantonskürzel für kantonale Wahlen
            - page_size (int): Einträge pro Seite
            - page (int): Seitennummer
            - response_format (str): 'markdown' oder 'json'

    Returns:
        str: Liste von Wahlen mit Datum, Bezeichnung und Wahl-ID
    """
    try:
        query_params: dict = {
            "pageSize": params.page_size,
            "pageNumber": params.page,
        }
        if params.year_from:
            query_params["yearFrom"] = params.year_from
        if params.year_to:
            query_params["yearTo"] = params.year_to
        if params.canton:
            query_params["canton"] = params.canton.upper()

        data = await _api_get(f"{POLIS_BASE}/elections", params=query_params)
    except Exception as e:
        return _handle_error(e)

    elections = data.get("electionList", data.get("elections", []))
    total = data.get("total", len(elections))

    if params.response_format == ResponseFormat.JSON:
        return json.dumps({"total": total, "elections": elections}, indent=2, ensure_ascii=False)

    if not elections:
        suggestions = []
        if params.canton:
            suggestions.append(
                f"canton-Filter entfernen (Wahlen für '{params.canton.upper()}' "
                f"sind möglicherweise nicht erfasst)"
            )
        if params.year_from and params.year_from > 1990:
            suggestions.append(f"year_from auf einen früheren Wert setzen (z.B. {params.year_from - 10})")
        if not suggestions:
            suggestions.append("Filter weglassen, um den vollen Datenbestand seit 1900 zu sehen")
        return (
            "Keine Wahlen gefunden mit den angegebenen Filtern. "
            "Vorschläge: " + "; ".join(suggestions) + "."
        )

    lines = ["## Schweizer Wahlen\n", f"*Total: {total} Wahlen, Seite {params.page}*\n"]
    for el in elections:
        el_date = el.get("date", el.get("electionDate", "?"))
        title = el.get("title", el.get("titleDe", "Unbekannt"))
        el_id = el.get("id", "?")
        lines.append(f"- **{el_date}** — {title} (ID: `{el_id}`)")

    return "\n".join(lines)


# ===========================================================================
# Entry point
# ===========================================================================

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
