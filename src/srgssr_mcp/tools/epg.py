"""EPG (Electronic Program Guide) tool."""

from mcp.server.fastmcp import Context
from pydantic import BaseModel, ConfigDict, Field

from srgssr_mcp._app import BusinessUnit, mcp
from srgssr_mcp._http import EPG_BASE, _api_get, _build_error_response
from srgssr_mcp._models import EpgProgram, EpgProgramsResponse, ToolErrorResponse
from srgssr_mcp.logging_config import get_logger

logger = get_logger("mcp.srgssr.epg")


class EpgProgramsInput(BaseModel):
    model_config = ConfigDict(strict=True, str_strip_whitespace=True, extra="forbid")
    business_unit: BusinessUnit = Field(
        ...,
        description="SRG SSR Unternehmenseinheit: 'srf', 'rts', 'rsi' (EPG für RTR/SWI nicht verfügbar)",
    )
    channel_id: str = Field(
        ..., min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$"
    )
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")


def _epg_program_from_dict(d: dict) -> EpgProgram:
    return EpgProgram(
        title=str(d.get("title", "Unbekannt")),
        start_time=d.get("startTime") or d.get("date"),
        subtitle=(d.get("subtitle") or "").strip() or None,
        description=(d.get("description") or d.get("lead") or "").strip()[:200] or None,
    )


def _build_epg_response(
    raw_programs: list, channel_id: str, bu: str, date: str
) -> EpgProgramsResponse:
    programs = [_epg_program_from_dict(p) for p in (raw_programs or [])]
    return EpgProgramsResponse(
        business_unit=bu,
        channel_id=channel_id,
        date=date,
        programs=programs,
        count=len(programs),
    )


@mcp.tool(
    name="srgssr_epg_get_programs",
    description=(
        "Ruft den vollständigen Programmplan (Electronic Program Guide) eines "
        "SRG SSR TV- oder Radiosenders für einen bestimmten Tag ab.\n\n"
        "<use_case>TV-/Radio-Programmvorschauen, redaktionelle Programm-Tipps.</use_case>\n\n"
        "<important_notes>Verfügbar nur für SRF, RTS und RSI — nicht für RTR "
        "oder SWI.</important_notes>\n\n"
        "<example>business_unit='srf', channel_id='srf1', date='2026-04-30'</example>"
    ),
    annotations={
        "title": "SRG SSR EPG – Programmvorschau",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def srgssr_epg_get_programs(
    params: EpgProgramsInput,
    ctx: Context | None = None,
) -> EpgProgramsResponse | ToolErrorResponse:
    bu = params.business_unit.value
    log = logger.bind(
        tool="srgssr_epg_get_programs",
        business_unit=bu,
        channel_id=params.channel_id,
        date=params.date,
    )
    log.info("tool_invoked")
    if ctx is not None:
        await ctx.info(
            "srgssr_epg_get_programs invoked",
            business_unit=bu,
            channel_id=params.channel_id,
            date=params.date,
        )
    try:
        data = await _api_get(
            f"{EPG_BASE}/programs",
            params={"bu": bu, "channel": params.channel_id, "date": params.date},
        )
    except Exception as e:
        log.error("tool_failed", error_type=type(e).__name__, error=str(e))
        return _build_error_response(
            e,
            not_found_hint=(
                f"channel_id='{params.channel_id}' nicht gefunden für "
                f"business_unit='{params.business_unit.value}'. Verwende "
                f"srgssr_video_get_livestreams oder srgssr_audio_get_livestreams, "
                f"um eine gültige channel_id zu finden. EPG ist nur für SRF, RTS "
                f"und RSI verfügbar."
            ),
        )

    raw_programs = data.get("programList", data.get("programs", []))
    log.info("tool_succeeded", program_count=len(raw_programs or []))
    return _build_epg_response(raw_programs, params.channel_id, bu, params.date)
