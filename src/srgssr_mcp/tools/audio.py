"""Audio tools: radio shows, episodes and livestreams across SRG SSR business units.

The shows-list and livestreams tools reuse the same input shape as their video
counterparts (:class:`VideoShowsInput`, :class:`VideoLivestreamsInput`); only
the upstream URL differs.
"""

from mcp.server.fastmcp import Context
from pydantic import BaseModel, ConfigDict, Field

from srgssr_mcp._app import BusinessUnit, mcp
from srgssr_mcp._http import AUDIO_BASE, _api_get, _build_error_response
from srgssr_mcp._models import (
    AudioChannel,
    AudioEpisode,
    AudioEpisodesResponse,
    AudioLivestreamsResponse,
    AudioShow,
    AudioShowsResponse,
    ToolErrorResponse,
)
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
        ..., min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_-]+$"
    )
    page_size: int | None = Field(default=10, ge=1, le=50)
    page: int | None = Field(default=1, ge=1)


def _audio_show_from_dict(d: dict) -> AudioShow:
    return AudioShow(
        id=str(d.get("id", "?")),
        title=str(d.get("title", d.get("name", "Unbekannt"))),
        description=(d.get("description") or d.get("lead") or "").strip() or None,
    )


def _audio_episode_from_dict(d: dict) -> AudioEpisode:
    return AudioEpisode(
        id=str(d.get("id", "?")),
        title=str(d.get("title", "Unbekannt")),
        date=d.get("date") or d.get("publishedDate"),
        duration_sec=d.get("duration") if isinstance(d.get("duration"), int) else None,
        description=(d.get("description") or d.get("lead") or "").strip() or None,
    )


def _audio_channel_from_dict(d: dict) -> AudioChannel:
    return AudioChannel(
        id=str(d.get("id", "?")),
        name=str(d.get("title", d.get("name", "Unbekannt"))),
    )


@mcp.tool(
    name="srgssr_audio_get_shows",
    description=(
        "Listet alle Radiosendungen einer SRG SSR Unternehmenseinheit auf.\n\n"
        "<use_case>Katalog-Browsing für Radio- und Podcast-Formate.</use_case>\n\n"
        "<important_notes>Audio-Kataloge enthalten häufig auch reine Podcasts.</important_notes>\n\n"
        "<example>business_unit='srf'</example>"
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
) -> AudioShowsResponse | ToolErrorResponse:
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
        return _build_error_response(e)

    raw_shows = data.get("showList", data.get("shows", [])) or []
    total = int(data.get("total", len(raw_shows)))
    log.info("tool_succeeded", result_count=len(raw_shows), total=total)

    shows = [_audio_show_from_dict(s) for s in raw_shows]
    offset = (params.page - 1) * params.page_size + len(shows)
    return AudioShowsResponse(
        business_unit=bu,
        page=params.page,
        page_size=params.page_size,
        total=total,
        shows=shows,
        count=len(shows),
        has_more=offset < total,
    )


@mcp.tool(
    name="srgssr_audio_get_episodes",
    description=(
        "Ruft die neuesten Episoden einer Radiosendung ab.\n\n"
        "<use_case>Auffinden konkreter Radiobeiträge oder Podcast-Folgen.</use_case>\n\n"
        "<important_notes>Episoden in chronologisch absteigender Reihenfolge.</important_notes>\n\n"
        "<example>business_unit='srf', show_id='echo'</example>"
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
) -> AudioEpisodesResponse | ToolErrorResponse:
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
        return _build_error_response(e)

    raw_episodes = data.get("episodeList", data.get("medias", [])) or []
    total = int(data.get("total", len(raw_episodes)))
    log.info("tool_succeeded", result_count=len(raw_episodes), total=total)

    episodes = [_audio_episode_from_dict(e) for e in raw_episodes]
    return AudioEpisodesResponse(
        business_unit=bu,
        show_id=params.show_id,
        page=params.page,
        page_size=params.page_size,
        total=total,
        episodes=episodes,
        count=len(episodes),
    )


@mcp.tool(
    name="srgssr_audio_get_livestreams",
    description=(
        "Listet alle Live-Radiosender einer SRG SSR Unternehmenseinheit auf.\n\n"
        "<use_case>Aufbau von Radio-Senderverzeichnissen, Live-Stream-Auswahl, "
        "Voraussetzung für srgssr_epg_get_programs (das eine channel_id "
        "benötigt). Für Live-TV stattdessen srgssr_video_get_livestreams "
        "verwenden, für Sendungsverzeichnisse srgssr_audio_get_shows.</use_case>\n\n"
        "<example>business_unit='srf'</example>"
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
) -> AudioLivestreamsResponse | ToolErrorResponse:
    bu = params.business_unit.value
    log = logger.bind(tool="srgssr_audio_get_livestreams", business_unit=bu)
    log.info("tool_invoked")
    if ctx is not None:
        await ctx.info("srgssr_audio_get_livestreams invoked", business_unit=bu)
    try:
        data = await _api_get(f"{AUDIO_BASE}/{bu}/channels")
    except Exception as e:
        log.error("tool_failed", error_type=type(e).__name__, error=str(e))
        return _build_error_response(e)

    raw_channels = data.get("channelList", data.get("channels", [])) or []
    log.info("tool_succeeded", result_count=len(raw_channels))

    channels = [_audio_channel_from_dict(c) for c in raw_channels]
    return AudioLivestreamsResponse(
        business_unit=bu,
        channels=channels,
        count=len(channels),
    )
