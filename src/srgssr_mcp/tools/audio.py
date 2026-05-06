"""Audio tools: radio shows, episodes and livestreams across SRG SSR business units.

The shows-list and livestreams tools reuse the same input shape as their video
counterparts (:class:`VideoShowsInput`, :class:`VideoLivestreamsInput`); only
the upstream URL differs.
"""

import json

from mcp.server.fastmcp import Context
from pydantic import BaseModel, ConfigDict, Field

from srgssr_mcp._app import VALID_BU, BusinessUnit, ResponseFormat, mcp
from srgssr_mcp._http import AUDIO_BASE, _api_get, _handle_error
from srgssr_mcp._provenance import provenance_footer, with_provenance
from srgssr_mcp.logging_config import get_logger
from srgssr_mcp.tools.video import VideoLivestreamsInput, VideoShowsInput

logger = get_logger("mcp.srgssr.audio")


class AudioEpisodesInput(BaseModel):
    model_config = ConfigDict(strict=True, str_strip_whitespace=True, extra="forbid")
    business_unit: BusinessUnit = Field(
        ...,
        description="SRG SSR Unternehmenseinheit: 'srf', 'rts', 'rsi', 'rtr' oder 'swi'",
    )
    show_id: str = Field(
        ...,
        description="Sendungs-ID aus srgssr_audio_get_shows",
        min_length=1,
        max_length=200,
        pattern=r"^[A-Za-z0-9_-]+$",
    )
    page_size: int | None = Field(default=10, ge=1, le=50, description="Episoden pro Seite")
    page: int | None = Field(default=1, ge=1, description="Seitennummer")
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Ausgabeformat: 'markdown' oder 'json'",
    )


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
async def srgssr_audio_get_shows(
    params: VideoShowsInput,
    ctx: Context | None = None,
) -> str:
    """Listet alle Radiosendungen einer SRG SSR Unternehmenseinheit auf (SRF, RTS, RSI, RTR, SWI).
    Gibt Sendungstitel, ID und Beschreibung zurück.

    Args:
        params (VideoShowsInput): Enthält:
            - business_unit (str): 'srf', 'rts', 'rsi', 'rtr' oder 'swi'
            - page_size (int): Einträge pro Seite (Standard: 20)
            - page (int): Seitennummer
            - response_format (str): 'markdown' oder 'json'
        ctx (Context, optional): FastMCP context for client-visible logging.

    Returns:
        str: Liste von Radiosendungen mit Titel, ID und Beschreibung
    """
    bu = params.business_unit.value
    log = logger.bind(
        tool="srgssr_audio_get_shows",
        business_unit=bu,
        page=params.page,
        page_size=params.page_size,
    )
    log.info("tool_invoked")
    if ctx is not None:
        await ctx.info("srgssr_audio_get_shows invoked", business_unit=bu)
    try:
        data = await _api_get(
            f"{AUDIO_BASE}/{bu}/showList",
            params={"pageSize": params.page_size, "pageNumber": params.page},
        )
    except Exception as e:
        log.error("tool_failed", error_type=type(e).__name__, error=str(e))
        return _handle_error(e)

    shows = data.get("showList", data.get("shows", []))
    total = data.get("total", len(shows))
    log.info("tool_succeeded", result_count=len(shows), total=total)

    if params.response_format == ResponseFormat.JSON:
        return json.dumps(
            with_provenance({"total": total, "shows": shows}),
            indent=2,
            ensure_ascii=False,
        )

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
    return "\n".join(lines) + provenance_footer()


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
async def srgssr_audio_get_episodes(
    params: AudioEpisodesInput,
    ctx: Context | None = None,
) -> str:
    """Ruft die neuesten Episoden einer Radiosendung ab. Benötigt die show_id aus srgssr_audio_get_shows.
    Gibt Episodentitel, Datum, Dauer und die Audio-ID für den Mediaplayer zurück.

    Args:
        params (AudioEpisodesInput): Enthält:
            - business_unit (str): 'srf', 'rts', 'rsi', 'rtr' oder 'swi'
            - show_id (str): Sendungs-ID
            - page_size (int): Episoden pro Seite
            - page (int): Seitennummer
            - response_format (str): 'markdown' oder 'json'
        ctx (Context, optional): FastMCP context for client-visible logging.

    Returns:
        str: Episodenliste mit Titel, Datum, Dauer und Audio-ID
    """
    bu = params.business_unit.value
    log = logger.bind(
        tool="srgssr_audio_get_episodes",
        business_unit=bu,
        show_id=params.show_id,
        page=params.page,
        page_size=params.page_size,
    )
    log.info("tool_invoked")
    if ctx is not None:
        await ctx.info(
            "srgssr_audio_get_episodes invoked",
            business_unit=bu,
            show_id=params.show_id,
        )
    try:
        data = await _api_get(
            f"{AUDIO_BASE}/{bu}/showEpisodesList/{params.show_id}",
            params={"pageSize": params.page_size, "pageNumber": params.page},
        )
    except Exception as e:
        log.error("tool_failed", error_type=type(e).__name__, error=str(e))
        return _handle_error(
            e,
            not_found_hint=(
                f"Verwende srgssr_audio_get_shows mit business_unit='{params.business_unit.value}', "
                f"um eine gültige show_id für '{params.show_id}' zu finden."
            ),
        )

    episodes = data.get("episodeList", data.get("medias", []))
    total = data.get("total", len(episodes))
    log.info("tool_succeeded", result_count=len(episodes), total=total)

    if params.response_format == ResponseFormat.JSON:
        return json.dumps(
            with_provenance({"total": total, "episodes": episodes}),
            indent=2,
            ensure_ascii=False,
        )

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
    return "\n".join(lines) + provenance_footer()


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
async def srgssr_audio_get_livestreams(
    params: VideoLivestreamsInput,
    ctx: Context | None = None,
) -> str:
    """Listet alle Live-Radiosender einer SRG SSR Unternehmenseinheit auf.
    Gibt Sendernamen und Kanal-IDs zurück, die mit dem SRG-Mediaplayer (Letterbox) genutzt werden können.

    Args:
        params (VideoLivestreamsInput): Enthält:
            - business_unit (str): 'srf', 'rts', 'rsi', 'rtr' oder 'swi'
            - response_format (str): 'markdown' oder 'json'

    Returns:
        str: Liste der Live-Radiosender mit Name und Kanal-ID
    """
    bu = params.business_unit.value
    log = logger.bind(tool="srgssr_audio_get_livestreams", business_unit=bu)
    log.info("tool_invoked")
    if ctx is not None:
        await ctx.info("srgssr_audio_get_livestreams invoked", business_unit=bu)
    try:
        data = await _api_get(f"{AUDIO_BASE}/{bu}/channels")
    except Exception as e:
        log.error("tool_failed", error_type=type(e).__name__, error=str(e))
        return _handle_error(e)

    channels = data.get("channelList", data.get("channels", []))
    log.info("tool_succeeded", result_count=len(channels))

    if params.response_format == ResponseFormat.JSON:
        return json.dumps(
            with_provenance(channels, list_key="channels"),
            indent=2,
            ensure_ascii=False,
        )

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
    return "\n".join(lines) + provenance_footer()
