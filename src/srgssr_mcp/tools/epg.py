"""EPG (Electronic Program Guide) tool."""

from mcp.server.mcpserver import Context
from pydantic import BaseModel, ConfigDict, Field

from srgssr_mcp._app import BusinessUnit, mcp
from srgssr_mcp._http import EPG_BASE, _api_get, _build_error_response
from srgssr_mcp._models import EpgProgram, EpgProgramsResponse, ToolErrorResponse
from srgssr_mcp.logging_config import get_logger

logger = get_logger("mcp.srgssr.epg")

# Harvested from the gateway itself rather than from documentation: an
# unsupported station name comes back as 400.01.004/005/006 with the valid
# inputs enumerated in the ``info`` field. Measured 2026-07-31 against
# https://api.srgssr.ch/epg/v3.
#
# Deliberately NOT enforced as input validation. If SRG SSR adds a station,
# a hard local check would reject a request the API would happily answer —
# refusing real data is the worse failure. The registry feeds the tool
# description (so the model picks a valid id up front) and the not-found hint
# (so a wrong id is recoverable in one step) and nothing else.
EPG_STATIONS: dict[tuple[str, str], tuple[str, ...]] = {
    ("srf", "tv"): ("srf-1", "srf-2", "srf-info"),
    ("srf", "radio"): (
        "srf-1",
        "srf-2",
        "srf-2-kultur",
        "srf-3",
        "srf-4",
        "srf-musikwelle",
        "srf-virus",
    ),
    ("rts", "tv"): ("rts-1", "rts-2", "rts-info"),
    ("rts", "radio"): ("LA1ERE", "ESPACE2", "COULEUR3", "OPTION_MUSIQUE"),
    ("rsi", "tv"): ("la-1", "la-2"),
    ("rsi", "radio"): ("rete-uno", "rete-due", "rete-tre"),
}


def _known_stations(bu: str, broadcast_type: str) -> str:
    """Render the known station ids for one (bu, broadcast_type) pair."""
    stations = EPG_STATIONS.get((bu, broadcast_type))
    return ", ".join(stations) if stations else "(keine bekannt)"


def _station_hint(bu: str, broadcast_type: str, channel_id: str) -> str:
    """Recovery hint naming the station ids the API accepts.

    The previous hint pointed at the livestream tools for discovery, which is
    a detour at best: their ids come from a different API and need not match
    the EPG's. Naming the accepted values makes a wrong id a one-step fix.
    """
    return (
        f"channel_id='{channel_id}' ist für business_unit='{bu}' und "
        f"broadcast_type='{broadcast_type}' nicht gültig. Bekannte Sender: "
        f"{_known_stations(bu, broadcast_type)}. Beachte die Schreibweise mit "
        f"Bindestrich ('srf-1', nicht 'srf1'). EPG gibt es nur für SRF, RTS "
        f"und RSI."
    )


def _station_overview() -> str:
    """One line per (bu, broadcast_type) for the tool description."""
    return "\n".join(f"{bu} {bt}: {', '.join(stations)}" for (bu, bt), stations in EPG_STATIONS.items())


class EpgProgramsInput(BaseModel):
    model_config = ConfigDict(strict=True, str_strip_whitespace=True, extra="forbid")
    business_unit: BusinessUnit = Field(
        ...,
        description="SRG SSR Unternehmenseinheit: 'srf', 'rts', 'rsi' (EPG für RTR/SWI nicht verfügbar)",
    )
    broadcast_type: str = Field(
        default="tv",
        pattern=r"^(tv|radio)$",
        description="Sendertyp: 'tv' oder 'radio'",
    )
    channel_id: str = Field(..., min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")


def _epg_station_url(bu: str, broadcast_type: str, channel_id: str) -> str:
    """Build the EPG station endpoint URL.

    The API keys a day's schedule off ``/{bu}/{tv|radio}/stations/{station}`` —
    business unit and broadcast type are path segments, not query parameters.
    Shared with the ``epg://`` resource in :mod:`srgssr_mcp.tools.resources` so
    the two surfaces cannot drift onto different endpoints.
    """
    return f"{EPG_BASE}/{bu}/{broadcast_type}/stations/{channel_id}"


def _extract_raw_programs(data: dict) -> list:
    """Pull the programme list out of an EPG payload.

    ``programs`` is what the station endpoint returns; ``programList`` is kept
    as a fallback so an older payload shape still parses.
    """
    return data.get("programs", data.get("programList", [])) or []


def _epg_program_from_dict(d: dict) -> EpgProgram:
    dates = d.get("dateTimes") or {}
    return EpgProgram(
        title=str(d.get("title", "Unbekannt")),
        start_time=dates.get("startTime") or d.get("startTime") or d.get("date"),
        subtitle=(d.get("shortDescription") or "").strip() or None,
        description=(d.get("longDescription") or d.get("description") or d.get("lead") or "").strip()[:200] or None,
    )


def _build_epg_response(raw_programs: list, channel_id: str, bu: str, date: str) -> EpgProgramsResponse:
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
        "oder SWI. Die channel_id ist eine Sender-Kennung der EPG-API und wird "
        "mit Bindestrich geschrieben ('srf-1', nicht 'srf1'); RTS-Radio "
        "verwendet Grossbuchstaben. Bekannte Sender:\n"
        f"{_station_overview()}</important_notes>\n\n"
        "<example>business_unit='srf', broadcast_type='tv', channel_id='srf-1', "
        "date='2026-04-30'</example>\n\n"
        "<example>business_unit='rsi', broadcast_type='radio', "
        "channel_id='rete-uno', date='2026-04-30'</example>"
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
            _epg_station_url(bu, params.broadcast_type, params.channel_id),
            params={"date": params.date},
        )
    except Exception as e:
        log.error("tool_failed", error_type=type(e).__name__, error=str(e))
        return _build_error_response(
            e,
            not_found_hint=_station_hint(bu, params.broadcast_type, params.channel_id),
        )

    raw_programs = _extract_raw_programs(data)
    log.info("tool_succeeded", program_count=len(raw_programs))
    return _build_epg_response(raw_programs, params.channel_id, bu, params.date)
