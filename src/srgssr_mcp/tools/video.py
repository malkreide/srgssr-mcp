"""Video tools: TV shows, episodes and livestreams across SRG SSR business units."""

import json

from mcp.server.fastmcp import Context
from pydantic import BaseModel, ConfigDict, Field

from srgssr_mcp._app import VALID_BU, BusinessUnit, ResponseFormat, mcp
from srgssr_mcp._http import VIDEO_BASE, _api_get, _handle_error
from srgssr_mcp.logging_config import get_logger

logger = get_logger("mcp.srgssr.video")


class VideoShowsInput(BaseModel):
    model_config = ConfigDict(strict=True, str_strip_whitespace=True, extra="forbid")
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


class VideoEpisodesInput(BaseModel):
    model_config = ConfigDict(strict=True, str_strip_whitespace=True, extra="forbid")
    business_unit: BusinessUnit = Field(
        ...,
        description="SRG SSR Unternehmenseinheit: 'srf', 'rts', 'rsi', 'rtr' oder 'swi'",
    )
    show_id: str = Field(
        ...,
        description="Sendungs-ID aus srgssr_video_get_shows (z.B. 'srf-tagesschau')",
        min_length=1,
        max_length=200,
        pattern=r"^[A-Za-z0-9_-]+$",
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


class VideoLivestreamsInput(BaseModel):
    model_config = ConfigDict(strict=True, str_strip_whitespace=True, extra="forbid")
    business_unit: BusinessUnit = Field(
        ...,
        description="SRG SSR Unternehmenseinheit: 'srf', 'rts', 'rsi', 'rtr' oder 'swi'",
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
async def srgssr_video_get_shows(
    params: VideoShowsInput,
    ctx: Context | None = None,
) -> str:
    """Listet alle TV-Sendungen einer SRG SSR Unternehmenseinheit auf (SRF, RTS, RSI, RTR, SWI).
    Gibt Sendungstitel, ID und Beschreibung zurück.

    Args:
        params (VideoShowsInput): Enthält:
            - business_unit (str): 'srf', 'rts', 'rsi', 'rtr' oder 'swi'
            - page_size (int): Einträge pro Seite (Standard: 20)
            - page (int): Seitennummer
            - response_format (str): 'markdown' oder 'json'
        ctx (Context, optional): FastMCP context for client-visible logging.

    Returns:
        str: Liste von TV-Sendungen mit Titel, ID und Beschreibung
    """
    bu = params.business_unit.value
    log = logger.bind(
        tool="srgssr_video_get_shows",
        business_unit=bu,
        page=params.page,
        page_size=params.page_size,
    )
    log.info("tool_invoked")
    if ctx is not None:
        await ctx.info("srgssr_video_get_shows invoked", business_unit=bu)
    try:
        data = await _api_get(
            f"{VIDEO_BASE}/{bu}/showList",
            params={"pageSize": params.page_size, "pageNumber": params.page},
        )
    except Exception as e:
        log.error("tool_failed", error_type=type(e).__name__, error=str(e))
        return _handle_error(e)

    shows = data.get("showList", data.get("shows", []))
    total = data.get("total", len(shows))
    log.info("tool_succeeded", result_count=len(shows), total=total)

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
async def srgssr_video_get_episodes(
    params: VideoEpisodesInput,
    ctx: Context | None = None,
) -> str:
    """Ruft die neuesten Episoden einer TV-Sendung ab. Benötigt die show_id aus srgssr_video_get_shows.
    Gibt Episodentitel, Datum, Dauer und die Video-ID für den Mediaplayer zurück.

    Args:
        params (VideoEpisodesInput): Enthält:
            - business_unit (str): 'srf', 'rts', 'rsi', 'rtr' oder 'swi'
            - show_id (str): Sendungs-ID
            - page_size (int): Episoden pro Seite
            - page (int): Seitennummer
            - response_format (str): 'markdown' oder 'json'
        ctx (Context, optional): FastMCP context for client-visible logging.

    Returns:
        str: Episodenliste mit Titel, Datum, Dauer und Video-ID
    """
    bu = params.business_unit.value
    log = logger.bind(
        tool="srgssr_video_get_episodes",
        business_unit=bu,
        show_id=params.show_id,
        page=params.page,
        page_size=params.page_size,
    )
    log.info("tool_invoked")
    if ctx is not None:
        await ctx.info(
            "srgssr_video_get_episodes invoked",
            business_unit=bu,
            show_id=params.show_id,
        )
    try:
        data = await _api_get(
            f"{VIDEO_BASE}/{bu}/showEpisodesList/{params.show_id}",
            params={"pageSize": params.page_size, "pageNumber": params.page},
        )
    except Exception as e:
        log.error("tool_failed", error_type=type(e).__name__, error=str(e))
        return _handle_error(
            e,
            not_found_hint=(
                f"Verwende srgssr_video_get_shows mit business_unit='{params.business_unit.value}', "
                f"um eine gültige show_id für '{params.show_id}' zu finden."
            ),
        )

    episodes = data.get("episodeList", data.get("medias", data.get("mediaList", [])))
    total = data.get("total", len(episodes))
    log.info("tool_succeeded", result_count=len(episodes), total=total)

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
async def srgssr_video_get_livestreams(
    params: VideoLivestreamsInput,
    ctx: Context | None = None,
) -> str:
    """Listet alle Live-TV-Sender einer SRG SSR Unternehmenseinheit auf.
    Gibt Sendernamen und Kanal-IDs zurück, die mit dem SRG-Mediaplayer (Pillarbox) genutzt werden können.

    Args:
        params (VideoLivestreamsInput): Enthält:
            - business_unit (str): 'srf', 'rts', 'rsi', 'rtr' oder 'swi'
            - response_format (str): 'markdown' oder 'json'

    Returns:
        str: Liste der Live-TV-Sender mit Name und Kanal-ID
    """
    bu = params.business_unit.value
    log = logger.bind(tool="srgssr_video_get_livestreams", business_unit=bu)
    log.info("tool_invoked")
    if ctx is not None:
        await ctx.info("srgssr_video_get_livestreams invoked", business_unit=bu)
    try:
        data = await _api_get(f"{VIDEO_BASE}/{bu}/channels")
    except Exception as e:
        log.error("tool_failed", error_type=type(e).__name__, error=str(e))
        return _handle_error(e)

    channels = data.get("channelList", data.get("channels", []))
    log.info("tool_succeeded", result_count=len(channels))

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
