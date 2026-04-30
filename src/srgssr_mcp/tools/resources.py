"""MCP Resources (ARCH-008).

Resources expose stable, cache-friendly data points behind URI templates so
clients can read them as passive context rather than invoking a parametrized
tool. EPG entries are stable for a given channel/date once published, and
votation/election results are immutable after the vote — both are natural
fits for the MCP Resource primitive. Tools remain available for parametrized
searches (year ranges, free-text, paginated listings).
"""

from srgssr_mcp._app import mcp
from srgssr_mcp._http import EPG_BASE, POLIS_BASE, _api_get, _handle_error
from srgssr_mcp.tools.epg import _format_epg_programs
from srgssr_mcp.tools.polis import _format_votation_result

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
        "Radiosenders als Markdown. Stabile Daten pro (bu, channel_id, date) — "
        "cache-freundlich. Verfügbar für SRF, RTS und RSI. Beispiel-URI: "
        "epg://srf/srf1/2026-04-30"
    ),
    mime_type="text/markdown",
)
async def epg_resource(bu: str, channel_id: str, date: str) -> str:
    """Read EPG programs for the given business unit, channel and date.

    URI template parameters:
        bu: 'srf', 'rts' or 'rsi' (RTR/SWI have no EPG).
        channel_id: channel identifier from the livestream listings (e.g. 'srf1').
        date: ISO date YYYY-MM-DD.
    """
    bu_norm = _normalize_bu(bu)
    if bu_norm not in {"srf", "rts", "rsi"}:
        return (
            f"## EPG nicht verfügbar\n\nUnternehmenseinheit '{bu}' wird vom EPG nicht "
            f"unterstützt. {_RESOURCE_BU_HINT}"
        )
    try:
        data = await _api_get(
            f"{EPG_BASE}/programs",
            params={"bu": bu_norm, "channel": channel_id, "date": date},
        )
    except Exception as e:
        return _handle_error(
            e,
            not_found_hint=(
                f"channel_id='{channel_id}' nicht gefunden für business_unit='{bu_norm}'. "
                f"Verwende das Tool srgssr_video_get_livestreams oder "
                f"srgssr_audio_get_livestreams, um eine gültige channel_id zu finden."
            ),
        )

    programs = data.get("programList", data.get("programs", []))
    return _format_epg_programs(programs, channel_id, bu_norm, date)


@mcp.resource(
    "votation://{votation_id}",
    name="srgssr_polis_votation",
    title="SRG SSR Polis – Abstimmungsresultate",
    description=(
        "Detaillierte Resultate einer Schweizer Volksabstimmung (Ja/Nein-Anteile, "
        "Stimmbeteiligung, kantonale Ergebnisse). Nach Abschluss einer Abstimmung "
        "immutable und damit cache-freundlich. Beispiel-URI: votation://v1"
    ),
    mime_type="text/markdown",
)
async def votation_resource(votation_id: str) -> str:
    """Read detailed results of a Swiss popular vote by its votation_id.

    Use the srgssr_polis_get_votations tool to discover available IDs.
    """
    try:
        data = await _api_get(f"{POLIS_BASE}/votations/{votation_id}")
    except Exception as e:
        return _handle_error(
            e,
            not_found_hint=(
                f"votation_id='{votation_id}' nicht gefunden. Verwende das Tool "
                f"srgssr_polis_get_votations, um gültige IDs zu ermitteln."
            ),
        )
    return _format_votation_result(data)
