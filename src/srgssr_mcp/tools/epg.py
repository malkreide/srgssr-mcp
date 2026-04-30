"""EPG (Electronic Program Guide) tool."""

import json

from pydantic import BaseModel, ConfigDict, Field

from srgssr_mcp._app import BusinessUnit, ResponseFormat, mcp
from srgssr_mcp._http import EPG_BASE, _api_get, _handle_error


class EpgProgramsInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    business_unit: BusinessUnit = Field(
        ...,
        description="SRG SSR Unternehmenseinheit: 'srf', 'rts', 'rsi' (EPG für RTR/SWI nicht verfügbar)",
    )
    channel_id: str = Field(
        ...,
        description="Kanal-ID aus srgssr_video_get_livestreams (z.B. 'srf1', 'rts1', 'rsi-la1')",
        min_length=1,
        max_length=100,
    )
    date: str = Field(
        ...,
        description="Datum im Format YYYY-MM-DD (z.B. '2025-03-08')",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Ausgabeformat: 'markdown' oder 'json'",
    )


@mcp.tool(
    name="srgssr_epg_get_programs",
    description=(
        "Ruft den vollständigen Programmplan (Electronic Program Guide) eines "
        "SRG SSR TV- oder Radiosenders für einen bestimmten Tag ab "
        "(Startzeit, Titel, Untertitel, Beschreibung).\n\n"
        "<use_case>TV-/Radio-Programmvorschauen, redaktionelle Programm-Tipps, "
        "Recherche zu historischen Sendeplätzen, Zuschauer-Empfehlungen oder "
        "Aufbau von Programm-Apps. Im Unterschied zu srgssr_video_get_episodes "
        "(Episoden einer einzelnen Sendung) liefert dieses Tool das gesamte "
        "Tagesprogramm eines Kanals chronologisch.</use_case>\n\n"
        "<important_notes>Verfügbar nur für SRF, RTS und RSI — nicht für RTR "
        "oder SWI. channel_id muss aus srgssr_video_get_livestreams oder "
        "srgssr_audio_get_livestreams stammen (z.B. 'srf1', 'rts1', 'rsi-la1'). "
        "Datum strikt im Format YYYY-MM-DD. Programmänderungen kurzfristig "
        "möglich; das EPG kann von der tatsächlichen Ausstrahlung abweichen.</important_notes>\n\n"
        "<example>business_unit='srf', channel_id='srf1', date='2026-04-30' | "
        "business_unit='rts', channel_id='rts1', date='2026-05-01'</example>"
    ),
    annotations={
        "title": "SRG SSR EPG – Programmvorschau",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def srgssr_epg_get_programs(params: EpgProgramsInput) -> str:
    """Ruft den Programmplan (Electronic Program Guide) für einen SRG SSR TV- oder Radiosender ab.
    Gibt alle Sendungen für einen bestimmten Tag zurück (Startzeit, Titel, Beschreibung).
    Unterstützt: SRF, RTS, RSI.

    Args:
        params (EpgProgramsInput): Enthält:
            - business_unit (str): 'srf', 'rts' oder 'rsi'
            - channel_id (str): Kanal-ID (z.B. 'srf1', 'rts1')
            - date (str): Datum YYYY-MM-DD
            - response_format (str): 'markdown' oder 'json'

    Returns:
        str: Programmliste des Tages mit Startuhrzeit, Titel und Beschreibung
    """
    try:
        bu = params.business_unit.value
        data = await _api_get(
            f"{EPG_BASE}/programs",
            params={"bu": bu, "channel": params.channel_id, "date": params.date},
        )
    except Exception as e:
        return _handle_error(
            e,
            not_found_hint=(
                f"channel_id='{params.channel_id}' nicht gefunden für "
                f"business_unit='{params.business_unit.value}'. Verwende "
                f"srgssr_video_get_livestreams oder srgssr_audio_get_livestreams, "
                f"um eine gültige channel_id zu finden. EPG ist nur für SRF, RTS "
                f"und RSI verfügbar."
            ),
        )

    programs = data.get("programList", data.get("programs", []))

    if params.response_format == ResponseFormat.JSON:
        return json.dumps(programs, indent=2, ensure_ascii=False)

    return _format_epg_programs(
        programs, params.channel_id, params.business_unit.value, params.date
    )


def _format_epg_programs(programs: list, channel_id: str, bu: str, date: str) -> str:
    if not programs:
        return (
            f"Keine Programmeinträge für channel_id='{channel_id}' "
            f"({bu.upper()}) am {date}. "
            f"Vorschläge: Datum prüfen (Format YYYY-MM-DD, sehr ferne Zukunft "
            f"oft nicht verfügbar), oder channel_id über "
            f"srgssr_video_get_livestreams verifizieren."
        )

    lines = [f"## Programm – {channel_id.upper()} ({bu.upper()}) am {date}\n"]
    for prog in programs:
        start = prog.get("startTime", prog.get("date", "?"))
        title = prog.get("title", "Unbekannt")
        subtitle = prog.get("subtitle", "")
        description = prog.get("description", prog.get("lead", "")).strip()[:100]
        lines.append(
            f"**{start}** — {title}"
            + (f": {subtitle}" if subtitle else "")
            + (f"\n  {description}" if description else "")
        )
    return "\n".join(lines)
