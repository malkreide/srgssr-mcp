"""Strict Pydantic Response models for every tool (SDK-002 Option A).

This module replaces the previous Markdown-string-with-Markdown-footer
convention with typed Pydantic ``BaseModel`` returns. Concrete benefits:

* FastMCP exposes an ``outputSchema`` per tool in the ``tools/list``
  manifest, so MCP clients can plan follow-up calls precisely instead of
  parsing free-form Markdown.
* The provenance metadata (``source``, ``license``, ``provenance_url``,
  ``fetched_at``) is enforced by the type system on every return path,
  including empty results and tool errors.
* The wire format is now a single, consistent JSON encoding. Markdown
  rendering — if a downstream consumer wants it — is the consumer's
  responsibility (the LLM client is well-equipped to render structured
  data as Markdown).

This is a **breaking change** for anyone who consumed the previous
Markdown / dual-format output. See ``CHANGELOG.md`` for the migration
note.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SOURCE: Literal["SRG SSR Public API V2"] = "SRG SSR Public API V2"
LICENSE: Literal[
    "SRG SSR Terms of Use (non-commercial; commercial use requires written permission via api@srgssr.ch)"
] = "SRG SSR Terms of Use (non-commercial; commercial use requires written permission via api@srgssr.ch)"
PROVENANCE_URL: Literal["https://developer.srgssr.ch"] = "https://developer.srgssr.ch"


def _utc_now() -> datetime:
    """UTC timestamp default factory; isolated for monkeypatching in tests."""
    return datetime.now(UTC)


class ProvenanceFields(BaseModel):
    """Mixin: every Response embeds these four fields verbatim.

    Kept as a flat top-level mixin (rather than nested ``provenance: {...}``)
    so MCP clients can pluck single attributes without descending one level.
    """

    model_config = ConfigDict(extra="forbid")

    source: Literal["SRG SSR Public API V2"] = Field(
        default=SOURCE, description="Upstream provider identity."
    )
    license: str = Field(default=LICENSE, description="Licensing terms.")
    provenance_url: Literal["https://developer.srgssr.ch"] = Field(
        default=PROVENANCE_URL,
        description="Canonical developer portal for the upstream API.",
    )
    fetched_at: datetime = Field(
        default_factory=_utc_now,
        description="UTC timestamp when this response was assembled.",
    )


# ---------------------------------------------------------------------------
# Generic error model
# ---------------------------------------------------------------------------

class ToolErrorResponse(ProvenanceFields):
    """Returned by any tool whose underlying call failed.

    The runtime ``error_type`` (``ValueError``, ``HTTPStatusError``, …) is
    helpful for clients deciding whether to retry; ``message`` is the
    sanitised human-facing text from :func:`srgssr_mcp._http._handle_error`.
    """

    is_error: Literal[True] = True
    error_type: str
    message: str


# ---------------------------------------------------------------------------
# Weather (4 tools)
# ---------------------------------------------------------------------------

class WeatherLocation(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    name: str
    canton: str | None = None
    postal_code: str | None = Field(default=None, alias="postalCode")


class WeatherLocationsResponse(ProvenanceFields):
    query: str
    matched_variant: str
    tried: list[str]
    locations: list[WeatherLocation]
    count: int


class WeatherCurrent(BaseModel):
    model_config = ConfigDict(extra="ignore")
    temperature_c: float | None
    weather_code: int | None
    wind_speed_kmh: float | None
    wind_direction_deg: float | None
    precipitation_mm: float | None
    relative_humidity_pct: float | None


class WeatherCurrentResponse(ProvenanceFields):
    latitude: float
    longitude: float
    geolocation_id: str | None
    current: WeatherCurrent


class WeatherHour(BaseModel):
    model_config = ConfigDict(extra="ignore")
    timestamp: str
    temperature_c: float | None
    precipitation_mm: float | None
    weather_code: int | None


class WeatherForecast24hResponse(ProvenanceFields):
    latitude: float
    longitude: float
    geolocation_id: str | None
    hours: list[WeatherHour]
    count: int


class WeatherDay(BaseModel):
    model_config = ConfigDict(extra="ignore")
    date: str
    temperature_min_c: float | None
    temperature_max_c: float | None
    precipitation_mm: float | None
    weather_code: int | None


class WeatherForecast7dayResponse(ProvenanceFields):
    latitude: float
    longitude: float
    geolocation_id: str | None
    days: list[WeatherDay]
    count: int


# ---------------------------------------------------------------------------
# Video (3 tools)
# ---------------------------------------------------------------------------

class VideoShow(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    title: str
    description: str | None = None


class VideoShowsResponse(ProvenanceFields):
    business_unit: str
    page: int
    page_size: int
    total: int
    shows: list[VideoShow]
    count: int
    has_more: bool


class VideoEpisode(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    title: str
    date: str | None = None
    duration_sec: int | None = None
    description: str | None = None


class VideoEpisodesResponse(ProvenanceFields):
    business_unit: str
    show_id: str
    page: int
    page_size: int
    total: int
    episodes: list[VideoEpisode]
    count: int


class VideoChannel(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    name: str


class VideoLivestreamsResponse(ProvenanceFields):
    business_unit: str
    channels: list[VideoChannel]
    count: int


# ---------------------------------------------------------------------------
# Audio (3 tools)
# ---------------------------------------------------------------------------

class AudioShow(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    title: str
    description: str | None = None


class AudioShowsResponse(ProvenanceFields):
    business_unit: str
    page: int
    page_size: int
    total: int
    shows: list[AudioShow]
    count: int
    has_more: bool


class AudioEpisode(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    title: str
    date: str | None = None
    duration_sec: int | None = None
    description: str | None = None


class AudioEpisodesResponse(ProvenanceFields):
    business_unit: str
    show_id: str
    page: int
    page_size: int
    total: int
    episodes: list[AudioEpisode]
    count: int


class AudioChannel(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    name: str


class AudioLivestreamsResponse(ProvenanceFields):
    business_unit: str
    channels: list[AudioChannel]
    count: int


# ---------------------------------------------------------------------------
# EPG (1 tool)
# ---------------------------------------------------------------------------

class EpgProgram(BaseModel):
    model_config = ConfigDict(extra="ignore")
    title: str
    start_time: str | None = None
    subtitle: str | None = None
    description: str | None = None


class EpgProgramsResponse(ProvenanceFields):
    business_unit: str
    channel_id: str
    date: str
    programs: list[EpgProgram]
    count: int


# ---------------------------------------------------------------------------
# Polis (3 tools)
# ---------------------------------------------------------------------------

class Votation(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    date: str | None = None
    title: str | None = None


class VotationsResponse(ProvenanceFields):
    year_from: int | None
    year_to: int | None
    canton: str | None
    page: int
    page_size: int
    total: int
    votations: list[Votation]
    count: int


class VotationResultResponse(ProvenanceFields):
    """Detailed votation result. ``result`` is the raw upstream payload —
    SRG SSR's Polis schema for results is large and nested, so we expose it
    as ``dict[str, Any]`` rather than mirroring every field."""

    votation_id: str
    title: str | None = None
    date: str | None = None
    result: dict[str, Any]


class Election(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    date: str | None = None
    title: str | None = None


class ElectionsResponse(ProvenanceFields):
    year_from: int | None
    year_to: int | None
    canton: str | None
    page: int
    page_size: int
    total: int
    elections: list[Election]
    count: int


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

class DailyBriefingResponse(ProvenanceFields):
    """Cross-domain composition: weather (24h) + EPG for one day.

    ``weather`` and ``epg`` are themselves typed responses; either side may
    be a :class:`ToolErrorResponse` if its upstream call failed
    (graceful-degradation contract).
    """

    business_unit: str
    channel_id: str
    date: str
    weather: WeatherForecast24hResponse | ToolErrorResponse
    epg: EpgProgramsResponse | ToolErrorResponse
