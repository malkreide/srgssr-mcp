"""MCP Resources (ARCH-008).

Resources expose stable, cache-friendly data points behind URI templates so
clients can read them as passive context rather than invoking a parametrized
tool. EPG entries are stable for a given channel/date once published, and
votation/election results are immutable after the vote — both are natural
fits for the MCP Resource primitive. Tools remain available for parametrized
searches (year ranges, free-text, paginated listings).

After SDK-002 Option A: resources return JSON-serialised typed responses
(``application/json``) — the same envelope shape that the corresponding
tools produce, so consumers can use a single parser for both surfaces.
"""

from srgssr_mcp._app import mcp
from srgssr_mcp._http import EPG_BASE, POLIS_BASE, _api_get, _build_error_response
from srgssr_mcp._models import VotationResultResponse
from srgssr_mcp.logging_config import get_logger
from srgssr_mcp.tools.epg import _build_epg_response

logger = get_logger("mcp.srgssr.resources")

_RESOURCE_BU_HINT = (
    "Erlaubte Unternehmenseinheiten: 'srf', 'rts', 'rsi'. EPG ist für RTR und SWI "
    "nicht verfügbar."
)


def _normalize_bu(bu: str) -> str:
    return bu.strip().lower()


@mcp.resource(
    "epg://{bu}/{channel_id}/{date}",
    name="srgssr_epg",
    title="SRG SSR EPG – Programmvorschau",
    description=(
        "Tagesprogramm (Electronic Program Guide) eines SRG SSR TV- oder "
        "Radiosenders als JSON-Envelope. Stabile Daten pro (bu, channel_id, "
        "date) — cache-freundlich. Verfügbar für SRF, RTS und RSI. "
        "Beispiel-URI: epg://srf/srf1/2026-04-30"
    ),
    mime_type="application/json",
)
async def epg_resource(bu: str, channel_id: str, date: str) -> str:
    """EPG programs for the given business unit, channel and date.

    URI template parameters:
        bu: 'srf', 'rts' or 'rsi' (RTR/SWI have no EPG).
        channel_id: channel identifier from the livestream listings (e.g. 'srf1').
        date: ISO date YYYY-MM-DD.
    """
    bu_norm = _normalize_bu(bu)
    log = logger.bind(
        resource="srgssr_epg",
        business_unit=bu_norm,
        channel_id=channel_id,
        date=date,
    )
    log.info("resource_invoked")
    if bu_norm not in {"srf", "rts", "rsi"}:
        log.warning("resource_unsupported_business_unit")
        return _build_error_response(
            ValueError(
                f"Unternehmenseinheit '{bu}' wird vom EPG nicht unterstützt. "
                f"{_RESOURCE_BU_HINT}"
            )
        ).model_dump_json(indent=2)
    try:
        data = await _api_get(
            f"{EPG_BASE}/programs",
            params={"bu": bu_norm, "channel": channel_id, "date": date},
        )
    except Exception as e:
        log.error("resource_failed", error_type=type(e).__name__, error=str(e))
        return _build_error_response(
            e,
            not_found_hint=(
                f"channel_id='{channel_id}' nicht gefunden für business_unit='{bu_norm}'. "
                f"Verwende das Tool srgssr_video_get_livestreams oder "
                f"srgssr_audio_get_livestreams, um eine gültige channel_id zu finden."
            ),
        ).model_dump_json(indent=2)

    raw_programs = data.get("programList", data.get("programs", []))
    log.info("resource_succeeded", program_count=len(raw_programs or []))
    response = _build_epg_response(raw_programs, channel_id, bu_norm, date)
    return response.model_dump_json(indent=2)


@mcp.resource(
    "votation://{votation_id}",
    name="srgssr_polis_votation",
    title="SRG SSR Polis – Abstimmungsresultate",
    description=(
        "Detaillierte Resultate einer Schweizer Volksabstimmung als JSON-Envelope "
        "(Ja/Nein-Anteile, Stimmbeteiligung, kantonale Ergebnisse). Nach Abschluss "
        "einer Abstimmung immutable und damit cache-freundlich. Beispiel-URI: "
        "votation://v1"
    ),
    mime_type="application/json",
)
async def votation_resource(votation_id: str) -> str:
    """Read detailed results of a Swiss popular vote by its votation_id.

    Use the srgssr_polis_get_votations tool to discover available IDs.
    """
    log = logger.bind(resource="srgssr_polis_votation", votation_id=votation_id)
    log.info("resource_invoked")
    try:
        data = await _api_get(f"{POLIS_BASE}/votations/{votation_id}")
    except Exception as e:
        log.error("resource_failed", error_type=type(e).__name__, error=str(e))
        return _build_error_response(
            e,
            not_found_hint=(
                f"votation_id='{votation_id}' nicht gefunden. Verwende das Tool "
                f"srgssr_polis_get_votations, um gültige IDs zu ermitteln."
            ),
        ).model_dump_json(indent=2)
    log.info("resource_succeeded")
    response = VotationResultResponse(
        votation_id=votation_id,
        title=data.get("title") or data.get("titleDe"),
        date=data.get("date") or data.get("votationDate"),
        result=data,
    )
    return response.model_dump_json(indent=2)
