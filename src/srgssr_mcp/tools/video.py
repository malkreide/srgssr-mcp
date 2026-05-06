"""Video tools: TV shows, episodes and livestreams across SRG SSR business units."""

from mcp.server.fastmcp import Context
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


class VideoShowsInput(BaseModel):
    model_config = ConfigDict(strict=True, str_strip_whitespace=True, extra="forbid")
    business_unit: BusinessUnit = Field(
        ...,
        description="SRG SSR Unternehmenseinheit: 'srf', 'rts', 'rsi', 'rtr' oder 'swi'",
    )
    page_size: int | None = Field(default=20, ge=1, le=100)
    page: int | None = Field(default=1, ge=1)


class VideoEpisodesInput(BaseModel):
    model_config = ConfigDict(strict=True, str_strip_whitespace=True, extra="forbid")
    business_unit: BusinessUnit = Field(
        ...,
        description="SRG SSR Unternehmenseinheit: 'srf', 'rts', 'rsi', 'rtr' oder 'swi'",
    )
    show_id: str = Field(
        ..., min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_-]+$"
    )
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


@mcp.tool(
    name="srgssr_video_get_shows",
    description=(
        "Listet alle TV-Sendungen einer SRG SSR Unternehmenseinheit auf "
        "(SRF, RTS, RSI, RTR, SWI) mit Sendungstitel, ID und Beschreibung.\n\n"
        "<use_case>Katalog-Browsing für TV-Sendungen, Programmanalysen.</use_case>\n\n"
        "<important_notes>Paginiert (page_size 1–100). Episoden über "
        "srgssr_video_get_episodes mit der show_id.</important_notes>\n\n"
        "<example>business_unit='srf'</example>"
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
        return _build_error_response(e)

    raw_shows = data.get("showList", data.get("shows", [])) or []
    total = int(data.get("total", len(raw_shows)))
    log.info("tool_succeeded", result_count=len(raw_shows), total=total)

    shows = [_show_from_dict(s) for s in raw_shows]
    offset = (params.page - 1) * params.page_size + len(shows)
    return VideoShowsResponse(
        business_unit=bu,
        page=params.page,
        page_size=params.page_size,
        total=total,
        shows=shows,
        count=len(shows),
        has_more=offset < total,
    )


@mcp.tool(
    name="srgssr_video_get_episodes",
    description=(
        "Ruft die neuesten Episoden einer TV-Sendung ab (Episodentitel, Datum, "
        "Dauer und Video-ID für den Mediaplayer Pillarbox).\n\n"
        "<use_case>Recherche zu konkreten Sendungsausgaben.</use_case>\n\n"
        "<important_notes>Episoden in chronologisch absteigender Reihenfolge. "
        "Paginiert mit page_size 1–50.</important_notes>\n\n"
        "<example>business_unit='srf', show_id='tagesschau'</example>"
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
            f"{VIDEO_BASE}/{bu}/showEpisodesList/{params.show_id}",
            params={"pageSize": params.page_size, "pageNumber": params.page},
        )
    except Exception as e:
        log.error("tool_failed", error_type=type(e).__name__, error=str(e))
        return _build_error_response(e)

    raw_episodes = data.get("episodeList", data.get("medias", [])) or []
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
        data = await _api_get(f"{VIDEO_BASE}/{bu}/channels")
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
