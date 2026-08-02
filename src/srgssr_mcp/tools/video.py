"""Video tools: TV shows, episodes and livestreams across SRG SSR business units."""

import asyncio
import string

from mcp.server.mcpserver import Context
from pydantic import BaseModel, ConfigDict, Field

from srgssr_mcp._app import BusinessUnit, mcp
from srgssr_mcp._http import VIDEO_BASE, _api_get, _build_error_response
from srgssr_mcp._models import (
    ToolErrorResponse,
    VideoChannel,
    VideoEpisode,
    VideoEpisodesResponse,
    VideoLivestreamsResponse,
    VideoShow,
    VideoShowsResponse,
)
from srgssr_mcp.logging_config import get_logger

logger = get_logger("mcp.srgssr.video")

# The v2 alphabetical listing is keyed by a single leading character; there is
# no "give me everything" call. These are the buckets the API accepts.
ALPHABET_BUCKETS: tuple[str, ...] = (*string.ascii_lowercase, "#")


class VideoShowsInput(BaseModel):
    model_config = ConfigDict(strict=True, str_strip_whitespace=True, extra="forbid")
    business_unit: BusinessUnit = Field(
        ...,
        description="SRG SSR Unternehmenseinheit: 'srf', 'rts', 'rsi', 'rtr' oder 'swi'",
    )
    character_filter: str | None = Field(
        default=None,
        pattern=r"^[a-z#]$",
        description=(
            "Anfangsbuchstabe der Sendungstitel: 'a'–'z' oder '#' für alles "
            "Übrige. Weglassen, um alle Buchstaben abzufragen."
        ),
    )
    page_size: int | None = Field(default=20, ge=1, le=100)
    page: int | None = Field(default=1, ge=1)


class VideoEpisodesInput(BaseModel):
    model_config = ConfigDict(strict=True, str_strip_whitespace=True, extra="forbid")
    business_unit: BusinessUnit = Field(
        ...,
        description="SRG SSR Unternehmenseinheit: 'srf', 'rts', 'rsi', 'rtr' oder 'swi'",
    )
    show_id: str = Field(..., min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_-]+$")
    page_size: int | None = Field(default=10, ge=1, le=50)
    page: int | None = Field(default=1, ge=1)


class VideoLivestreamsInput(BaseModel):
    model_config = ConfigDict(strict=True, str_strip_whitespace=True, extra="forbid")
    business_unit: BusinessUnit = Field(
        ...,
        description="SRG SSR Unternehmenseinheit: 'srf', 'rts', 'rsi', 'rtr' oder 'swi'",
    )


def _show_from_dict(d: dict) -> VideoShow:
    return VideoShow(
        id=str(d.get("id", "?")),
        title=str(d.get("title", d.get("name", "Unbekannt"))),
        description=(d.get("description") or d.get("lead") or "").strip() or None,
    )


def _episode_from_dict(d: dict) -> VideoEpisode:
    return VideoEpisode(
        id=str(d.get("id", "?")),
        title=str(d.get("title", "Unbekannt")),
        date=d.get("date") or d.get("publishedDate"),
        duration_sec=d.get("duration") if isinstance(d.get("duration"), int) else None,
        description=(d.get("description") or d.get("lead") or "").strip() or None,
    )


def _channel_from_dict(d: dict) -> VideoChannel:
    return VideoChannel(
        id=str(d.get("id", "?")),
        name=str(d.get("title", d.get("name", "Unbekannt"))),
    )


def _extract_shows(data: dict) -> list:
    """Pull the show list out of a ShowList payload."""
    return data.get("showList", data.get("shows", [])) or []


async def _fetch_show_bucket(bu: str, character: str, page_size: int) -> dict | Exception:
    """One alphabetical bucket. Returns the exception instead of raising.

    The caller fans out over 27 of these; one failing letter must not sink the
    whole listing. But the exception is carried back rather than dropped, so
    the caller can tell "this letter has no shows" from "this letter could not
    be fetched" — a total outage has to surface as an error, not as an empty
    catalogue.
    """
    try:
        data = await _api_get(
            f"{VIDEO_BASE}/tv_shows/alphabetical",
            params={"bu": bu, "characterFilter": character, "pageSize": page_size},
        )
    except Exception as e:  # noqa: BLE001 — returned to the caller, not swallowed
        logger.warning(
            "show_bucket_failed",
            business_unit=bu,
            character=character,
            error_type=type(e).__name__,
        )
        return e
    return data


@mcp.tool(
    name="srgssr_video_get_shows",
    description=(
        "Listet TV-Sendungen einer SRG SSR Unternehmenseinheit auf "
        "(SRF, RTS, RSI, RTR, SWI) mit Sendungstitel, ID und Beschreibung.\n\n"
        "<use_case>Katalog-Browsing für TV-Sendungen, Programmanalysen.</use_case>\n\n"
        "<important_notes>Die API gruppiert Sendungen nach Anfangsbuchstabe. "
        "Ohne character_filter werden alle Buchstaben abgefragt und "
        "zusammengeführt — das sind 27 Abfragen, also nur nutzen, wenn "
        "wirklich der ganze Katalog gebraucht wird. Mit character_filter ist "
        "es eine einzige Abfrage. page_size gilt pro Buchstabe. Episoden über "
        "srgssr_video_get_episodes mit der show_id.</important_notes>\n\n"
        "<example>business_unit='srf', character_filter='t'</example>"
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
) -> VideoShowsResponse | ToolErrorResponse:
    bu = params.business_unit.value
    log = logger.bind(
        tool="srgssr_video_get_shows",
        business_unit=bu,
        character_filter=params.character_filter,
        page=params.page,
        page_size=params.page_size,
    )
    log.info("tool_invoked")
    if ctx is not None:
        await ctx.info("srgssr_video_get_shows invoked", business_unit=bu)

    if params.character_filter is not None:
        # Single bucket: let the error surface so the caller sees why.
        try:
            data = await _api_get(
                f"{VIDEO_BASE}/tv_shows/alphabetical",
                params={
                    "bu": bu,
                    "characterFilter": params.character_filter,
                    "pageSize": params.page_size,
                },
            )
        except Exception as e:
            log.error("tool_failed", error_type=type(e).__name__, error=str(e))
            return _build_error_response(e)
        raw_shows = _extract_shows(data)
        has_more = bool(data.get("next"))
    else:
        buckets = await asyncio.gather(
            *(_fetch_show_bucket(bu, character, params.page_size) for character in ALPHABET_BUCKETS)
        )
        # Deduplicate across buckets: a show can only sit in one, but the API
        # is not ours to assume that about.
        failures = [b for b in buckets if isinstance(b, Exception)]
        if len(failures) == len(ALPHABET_BUCKETS):
            # Every letter failed — that is an outage, not an empty catalogue.
            # Returning [] here would have the model report "no shows".
            log.error("tool_failed", error_type=type(failures[0]).__name__)
            return _build_error_response(failures[0])
        if failures:
            log.warning("partial_result", failed_buckets=len(failures))
        seen: set[str] = set()
        raw_shows = []
        has_more = False
        for bucket in buckets:
            if isinstance(bucket, Exception):
                continue
            has_more = has_more or bool(bucket.get("next"))
            for show in _extract_shows(bucket):
                show_id = str(show.get("id", ""))
                if show_id and show_id in seen:
                    continue
                seen.add(show_id)
                raw_shows.append(show)

    # v2 reports no catalogue size, only an opaque `next` cursor — so `total`
    # is what this call actually returned, and `has_more` carries the rest.
    total = len(raw_shows)
    log.info("tool_succeeded", result_count=len(raw_shows), total=total)

    shows = [_show_from_dict(s) for s in raw_shows]
    return VideoShowsResponse(
        business_unit=bu,
        page=params.page,
        page_size=params.page_size,
        total=total,
        shows=shows,
        count=len(shows),
        has_more=has_more,
    )


@mcp.tool(
    name="srgssr_video_get_episodes",
    description=(
        "Ruft die neuesten Episoden einer TV-Sendung ab (Episodentitel, Datum, "
        "Dauer und Video-ID für den Mediaplayer Pillarbox).\n\n"
        "<use_case>Recherche zu konkreten Sendungsausgaben.</use_case>\n\n"
        "<important_notes>Episoden in chronologisch absteigender Reihenfolge. "
        "Paginiert mit page_size 1–50.</important_notes>\n\n"
        "<example>business_unit='srf', show_id='tagesschau'</example>\n\n"
        "<important_notes>Gültige show_id liefert srgssr_video_get_shows.</important_notes>"
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
) -> VideoEpisodesResponse | ToolErrorResponse:
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
            f"{VIDEO_BASE}/latest_episodes/shows/{params.show_id}",
            params={"bu": bu, "pageSize": params.page_size},
        )
    except Exception as e:
        log.error("tool_failed", error_type=type(e).__name__, error=str(e))
        return _build_error_response(e)

    # `episodeComposition` is what the v2 EpisodeComposition payload carries;
    # the older names stay as fallbacks.
    raw_episodes = data.get("episodeComposition") or data.get("episodeList") or data.get("medias") or []
    total = int(data.get("total", len(raw_episodes)))
    log.info("tool_succeeded", result_count=len(raw_episodes), total=total)

    episodes = [_episode_from_dict(e) for e in raw_episodes]
    return VideoEpisodesResponse(
        business_unit=bu,
        show_id=params.show_id,
        page=params.page,
        page_size=params.page_size,
        total=total,
        episodes=episodes,
        count=len(episodes),
    )


@mcp.tool(
    name="srgssr_video_get_livestreams",
    description=(
        "Listet alle Live-TV-Sender einer SRG SSR Unternehmenseinheit auf.\n\n"
        "<use_case>Live-Stream-Auswahl, Voraussetzung für srgssr_epg_get_programs "
        "(das eine channel_id benötigt).</use_case>\n\n"
        "<important_notes>RTR und SWI haben weniger oder keine Live-Kanäle.</important_notes>\n\n"
        "<example>business_unit='srf'</example>"
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
) -> VideoLivestreamsResponse | ToolErrorResponse:
    bu = params.business_unit.value
    log = logger.bind(tool="srgssr_video_get_livestreams", business_unit=bu)
    log.info("tool_invoked")
    if ctx is not None:
        await ctx.info("srgssr_video_get_livestreams invoked", business_unit=bu)
    try:
        data = await _api_get(f"{VIDEO_BASE}/tv_channels", params={"bu": bu})
    except Exception as e:
        log.error("tool_failed", error_type=type(e).__name__, error=str(e))
        return _build_error_response(e)

    raw_channels = data.get("channelList", data.get("channels", [])) or []
    log.info("tool_succeeded", result_count=len(raw_channels))

    channels = [_channel_from_dict(c) for c in raw_channels]
    return VideoLivestreamsResponse(
        business_unit=bu,
        channels=channels,
        count=len(channels),
    )
