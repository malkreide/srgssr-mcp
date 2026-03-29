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
"""

import base64
import json
import os
import time
from enum import StrEnum

import httpx
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field

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
# Token management (simple in-memory cache)
# ---------------------------------------------------------------------------

_token_cache: dict = {"access_token": None, "expires_at": 0.0}


def _get_credentials() -> tuple[str, str]:
    key = os.environ.get("SRGSSR_CONSUMER_KEY", "")
    secret = os.environ.get("SRGSSR_CONSUMER_SECRET", "")
    if not key or not secret:
        raise ValueError(
            "SRGSSR_CONSUMER_KEY and SRGSSR_CONSUMER_SECRET must be set. "
            "Register at https://developer.srgssr.ch to obtain credentials."
        )
    return key, secret


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


def _handle_error(e: Exception) -> str:
    if isinstance(e, ValueError):
        return f"Konfigurationsfehler: {e}"
    if isinstance(e, httpx.HTTPStatusError):
        sc = e.response.status_code
        if sc == 401:
            return "Fehler 401: Ungültige API-Credentials. Bitte SRGSSR_CONSUMER_KEY und SRGSSR_CONSUMER_SECRET prüfen."
        if sc == 403:
            return "Fehler 403: Zugriff verweigert. Möglicherweise fehlt der Zugriff auf diese API im gewählten Produkt."
        if sc == 404:
            return "Fehler 404: Ressource nicht gefunden. Bitte ID oder Parameter prüfen."
        if sc == 429:
            return "Fehler 429: Rate-Limit überschritten. Bitte etwas warten und erneut versuchen."
        return f"API-Fehler {sc}: {e.response.text[:200]}"
    if isinstance(e, httpx.TimeoutException):
        return "Fehler: Anfrage hat das Timeout überschritten. Bitte erneut versuchen."
    return f"Unerwarteter Fehler ({type(e).__name__}): {e}"


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
    try:
        data = await _api_get(
            f"{WEATHER_BASE}/geolocations",
            params={"searchterm": params.query},
        )
    except Exception as e:
        return _handle_error(e)

    locations = data.get("geolocationList", [])
    if not locations:
        return f"Keine Standorte gefunden für: '{params.query}'. Bitte anderen Suchbegriff verwenden."

    if params.response_format == ResponseFormat.JSON:
        return json.dumps(locations, indent=2, ensure_ascii=False)

    lines = [f"## Gefundene Standorte für '{params.query}'\n"]
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
    lines = ["## 24-Stunden-Prognose (SRF Meteo)\n", "| Stunde | Temp °C | Niederschlag | Wetterlage |", "| --- | --- | --- | --- |"]
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
    lines = ["## 7-Tages-Prognose (SRF Meteo)\n", "| Datum | Min °C | Max °C | Niederschlag | Wetterlage |", "| --- | --- | --- | --- | --- |"]
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
        return _handle_error(e)

    episodes = data.get("episodeList", data.get("medias", data.get("mediaList", [])))
    total = data.get("total", len(episodes))

    if params.response_format == ResponseFormat.JSON:
        return json.dumps({"total": total, "episodes": episodes}, indent=2, ensure_ascii=False)

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
        return _handle_error(e)

    episodes = data.get("episodeList", data.get("medias", []))
    total = data.get("total", len(episodes))

    if params.response_format == ResponseFormat.JSON:
        return json.dumps({"total": total, "episodes": episodes}, indent=2, ensure_ascii=False)

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
        return _handle_error(e)

    programs = data.get("programList", data.get("programs", []))

    if params.response_format == ResponseFormat.JSON:
        return json.dumps(programs, indent=2, ensure_ascii=False)

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
        description="Kantonskürzel für kantonale Abstimmungen (z.B. 'ZH', 'BE', 'GE'). Leer für nationale Abstimmungen.",
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

    lines = [f"## Schweizer Volksabstimmungen ({filter_str})\n", f"*Total: {total} Abstimmungen, Seite {params.page}*\n"]
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
        return _handle_error(e)

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

if __name__ == "__main__":
    mcp.run()

