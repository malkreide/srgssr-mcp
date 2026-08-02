"""Audio tools: radio shows, episodes and livestreams across SRG SSR business units.

The livestreams tool reuses the video input shape
(:class:`VideoLivestreamsInput`); only the upstream URL differs. The shows
listing cannot: the v2 radio endpoint is keyed by channel as well as by
leading character, so it carries its own :class:`AudioShowsInput`.
"""

import asyncio

from mcp.server.mcpserver import Context
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
from srgssr_mcp.tools.video import ALPHABET_BUCKETS, VideoLivestreamsInput

logger = get_logger("mcp.srgssr.audio")


def _extract_shows(data: dict) -> list:
    return data.get("showList", data.get("shows", [])) or []


async def _fetch_show_bucket(bu: str, channel_id: str, character: str, page_size: int) -> dict | Exception:
    """One alphabetical bucket for one channel. Returns the exception instead
    of raising, so the caller can tell an empty letter from a failed one."""
    try:
        data = await _api_get(
            f"{AUDIO_BASE}/radioshows/byChannel",
            params={
                "bu": bu,
                "channelId": channel_id,
                "characterFilter": character,
                "pageSize": page_size,
            },
        )
    except Exception as e:  # noqa: BLE001 — returned to the caller, not swallowed
        logger.warning(
            "show_bucket_failed",
            business_unit=bu,
            channel_id=channel_id,
            character=character,
            error_type=type(e).__name__,
        )
        return e
    return data


class AudioShowsInput(BaseModel):
    model_config = ConfigDict(strict=True, str_strip_whitespace=True, extra="forbid")
    business_unit: BusinessUnit = Field(
        ...,
        description="SRG SSR Unternehmenseinheit: 'srf', 'rts', 'rsi', 'rtr' oder 'swi'",
    )
    channel_id: str = Field(
        ...,
        min_length=1,
        max_length=200,
        pattern=r"^[A-Za-z0-9_-]+$",
        description=(
            "Radiokanal-ID. Die v2-API listet Radiosendungen nur pro Kanal — "
            "gültige IDs liefert srgssr_audio_get_livestreams."
        ),
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


class AudioEpisodesInput(BaseModel):
    model_config = ConfigDict(strict=True, str_strip_whitespace=True, extra="forbid")
    business_unit: BusinessUnit = Field(
        ...,
        description="SRG SSR Unternehmenseinheit: 'srf', 'rts', 'rsi', 'rtr' oder 'swi'",
    )
    show_id: str = Field(..., min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_-]+$")
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
        "Listet Radiosendungen eines SRG SSR Radiokanals auf.\n\n"
        "<use_case>Katalog-Browsing für Radio- und Podcast-Formate.</use_case>\n\n"
        "<important_notes>Die API listet Radiosendungen nur pro Kanal — "
        "channel_id ist Pflicht und stammt aus srgssr_audio_get_livestreams. "
        "Innerhalb eines Kanals sind die Sendungen nach Anfangsbuchstabe "
        "gruppiert: ohne character_filter werden alle 27 Buchstaben abgefragt "
        "und zusammengeführt, mit character_filter ist es eine einzige "
        "Abfrage. Audio-Kataloge enthalten häufig auch reine "
        "Podcasts.</important_notes>\n\n"
        "<example>business_unit='srf', channel_id='69e8ac16-4327-4af4-b873-fd5cd6e895a7', "
        "character_filter='e'</example>"
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
    params: AudioShowsInput,
    ctx: Context | None = None,
) -> AudioShowsResponse | ToolErrorResponse:
    bu = params.business_unit.value
    log = logger.bind(
        tool="srgssr_audio_get_shows",
        business_unit=bu,
        channel_id=params.channel_id,
        character_filter=params.character_filter,
        page=params.page,
        page_size=params.page_size,
    )
    log.info("tool_invoked")
    if ctx is not None:
        await ctx.info("srgssr_audio_get_shows invoked", business_unit=bu)

    if params.character_filter is not None:
        try:
            data = await _api_get(
                f"{AUDIO_BASE}/radioshows/byChannel",
                params={
                    "bu": bu,
                    "channelId": params.channel_id,
                    "characterFilter": params.character_filter,
                    "pageSize": params.page_size,
                },
            )
        except Exception as e:
            log.error("tool_failed", error_type=type(e).__name__, error=str(e))
            return _build_error_response(
                e,
                not_found_hint=(
                    f"channel_id='{params.channel_id}' nicht gefunden. Gültige "
                    f"Radiokanal-IDs liefert srgssr_audio_get_livestreams."
                ),
            )
        raw_shows = _extract_shows(data)
        has_more = bool(data.get("next"))
    else:
        buckets = await asyncio.gather(
            *(_fetch_show_bucket(bu, params.channel_id, character, params.page_size) for character in ALPHABET_BUCKETS)
        )
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

    total = len(raw_shows)
    log.info("tool_succeeded", result_count=len(raw_shows), total=total)

    shows = [_audio_show_from_dict(s) for s in raw_shows]
    return AudioShowsResponse(
        business_unit=bu,
        page=params.page,
        page_size=params.page_size,
        total=total,
        shows=shows,
        count=len(shows),
        has_more=has_more,
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
            f"{AUDIO_BASE}/episodeComposition/shows/{params.show_id}",
            params={"bu": bu, "pageSize": params.page_size},
        )
    except Exception as e:
        log.error("tool_failed", error_type=type(e).__name__, error=str(e))
        return _build_error_response(e)

    raw_episodes = data.get("episodeComposition") or data.get("episodeList") or data.get("medias") or []
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
        "<important_notes>RTR und SWI haben weniger oder keine Live-Kanäle; "
        "eine andere Unternehmenseinheit liefert in der Regel mehr "
        "Resultate.</important_notes>\n\n"
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
        data = await _api_get(f"{AUDIO_BASE}/radio/channels", params={"bu": bu})
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
