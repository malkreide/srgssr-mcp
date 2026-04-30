"""Polis tools: Swiss votations, votation results, and elections (since 1900)."""

import json

from pydantic import BaseModel, ConfigDict, Field

from srgssr_mcp._app import ResponseFormat, mcp
from srgssr_mcp._http import POLIS_BASE, _api_get, _handle_error
from srgssr_mcp.logging_config import get_logger

logger = get_logger("mcp.srgssr.polis")


class PolisListInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    year_from: int | None = Field(
        default=None,
        description="Startjahr der Abfrage (z.B. 2000). Minimum: 1900",
        ge=1900,
        le=2100,
    )
    year_to: int | None = Field(
        default=None,
        description="Endjahr der Abfrage (z.B. 2024)",
        ge=1900,
        le=2100,
    )
    canton: str | None = Field(
        default=None,
        description=(
            "Kantonskürzel für kantonale Abstimmungen (z.B. 'ZH', 'BE', 'GE')."
            " Leer für nationale Abstimmungen."
        ),
        max_length=4,
    )
    page_size: int | None = Field(default=20, ge=1, le=100, description="Einträge pro Seite")
    page: int | None = Field(default=1, ge=1, description="Seitennummer")
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Ausgabeformat: 'markdown' oder 'json'",
    )


class PolisResultInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    votation_id: str = Field(
        ...,
        description="Abstimmungs-ID aus srgssr_polis_get_votations",
        min_length=1,
        max_length=100,
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Ausgabeformat: 'markdown' oder 'json'",
    )


@mcp.tool(
    name="srgssr_polis_get_votations",
    description=(
        "Ruft Schweizer Volksabstimmungen und Referenden (national und kantonal) "
        "aus dem Polis-System ab. Liefert Datum, Titel und votation_id pro Eintrag.\n\n"
        "<use_case>Historische Analysen von Abstimmungsverhalten, journalistische "
        "Recherchen zu direkter Demokratie, Bildungszwecke für Schweizer Politik, "
        "Trendanalysen über Kantone und Zeiträume. Erster Schritt, um eine "
        "votation_id für srgssr_polis_get_votation_results zu ermitteln. Für "
        "Wahlen (Nationalrat, Ständerat) stattdessen "
        "srgssr_polis_get_elections.</use_case>\n\n"
        "<important_notes>Daten reichen zurück bis 1900. Filter nach Jahr "
        "(year_from/year_to, beide 1900–2100) und Kanton möglich. Ohne canton-Filter "
        "werden nationale Abstimmungen geliefert; mit Kantonskürzel ('ZH', 'BE', "
        "'GE' …) kantonale. Liefert nur Metadaten — detaillierte Resultate "
        "(Ja/Nein-Anteile, Stimmbeteiligung) über srgssr_polis_get_votation_results. "
        "Paginiert mit page_size 1–100.</important_notes>\n\n"
        "<example>year_from=2020, year_to=2024 | canton='ZH', year_from=2000 | "
        "page_size=50, page=1</example>"
    ),
    annotations={
        "title": "SRG SSR Polis – Schweizer Abstimmungen",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def srgssr_polis_get_votations(params: PolisListInput) -> str:
    """Ruft Schweizer Volksabstimmungen und Referenden aus dem Polis-System ab.
    Daten reichen zurück bis 1900. Kann nach Jahr und Kanton gefiltert werden.
    Ideal für historische Analysen, Bildungszwecke und journalistische Recherchen.

    Args:
        params (PolisListInput): Enthält:
            - year_from (Optional[int]): Startjahr (Standard: alle)
            - year_to (Optional[int]): Endjahr (Standard: alle)
            - canton (Optional[str]): Kantonskürzel (z.B. 'ZH') oder leer für national
            - page_size (int): Einträge pro Seite
            - page (int): Seitennummer
            - response_format (str): 'markdown' oder 'json'

    Returns:
        str: Liste von Abstimmungen mit Datum, Titel und Abstimmungs-ID
    """
    log = logger.bind(
        tool="srgssr_polis_get_votations",
        year_from=params.year_from,
        year_to=params.year_to,
        canton=params.canton.upper() if params.canton else None,
        page=params.page,
        page_size=params.page_size,
    )
    log.info("tool_invoked")
    try:
        query_params: dict = {
            "pageSize": params.page_size,
            "pageNumber": params.page,
        }
        if params.year_from:
            query_params["yearFrom"] = params.year_from
        if params.year_to:
            query_params["yearTo"] = params.year_to
        if params.canton:
            query_params["canton"] = params.canton.upper()

        data = await _api_get(f"{POLIS_BASE}/votations", params=query_params)
    except Exception as e:
        log.error("tool_failed", error_type=type(e).__name__, error=str(e))
        return _handle_error(e)

    votations = data.get("votationList", data.get("votations", []))
    total = data.get("total", len(votations))
    log.info("tool_succeeded", result_count=len(votations), total=total)

    if params.response_format == ResponseFormat.JSON:
        return json.dumps({"total": total, "votations": votations}, indent=2, ensure_ascii=False)

    filter_desc = []
    if params.year_from or params.year_to:
        filter_desc.append(f"Jahre {params.year_from or '1900'}–{params.year_to or 'heute'}")
    if params.canton:
        filter_desc.append(f"Kanton {params.canton.upper()}")
    filter_str = " | ".join(filter_desc) if filter_desc else "alle"

    if not votations:
        suggestions = []
        if params.canton:
            suggestions.append(
                f"canton-Filter entfernen (kantonale Abstimmungen für "
                f"'{params.canton.upper()}' sind möglicherweise nicht erfasst)"
            )
        if params.year_from and params.year_from > 1990:
            suggestions.append(f"year_from auf einen früheren Wert setzen (z.B. {params.year_from - 10})")
        if params.year_to and params.year_to < 2024:
            suggestions.append(f"year_to auf einen späteren Wert setzen (z.B. {params.year_to + 10})")
        if not suggestions:
            suggestions.append("Filter weglassen, um den vollen Datenbestand seit 1900 zu sehen")
        return (
            f"Keine Volksabstimmungen gefunden ({filter_str}). "
            f"Vorschläge: " + "; ".join(suggestions) + "."
        )

    lines = [
        f"## Schweizer Volksabstimmungen ({filter_str})\n",
        f"*Total: {total} Abstimmungen, Seite {params.page}*\n",
    ]
    for v in votations:
        v_date = v.get("date", v.get("votationDate", "?"))
        title = v.get("title", v.get("titleDe", "Unbekannt"))
        v_id = v.get("id", "?")
        lines.append(f"- **{v_date}** — {title} (ID: `{v_id}`)")

    return "\n".join(lines)


@mcp.tool(
    name="srgssr_polis_get_votation_results",
    description=(
        "Ruft detaillierte Resultate einer einzelnen Schweizer Volksabstimmung ab "
        "(Ja/Nein-Anteile, Stimmbeteiligung, kantonale Ergebnisse, "
        "Annahme/Ablehnung).\n\n"
        "<use_case>Vertiefte politische Analysen, Visualisierung kantonaler "
        "Unterschiede, redaktionelle Aufbereitung von Abstimmungs-Sonntagen, "
        "Vergleiche zwischen Sprachregionen oder Stadt/Land. Im Unterschied zu "
        "srgssr_polis_get_votations (Liste mit Metadaten) liefert dieses Tool "
        "die vollständigen Resultate einer einzelnen Abstimmung.</use_case>\n\n"
        "<important_notes>Erfordert eine votation_id, die zuvor über "
        "srgssr_polis_get_votations ermittelt wurde. Bei sehr aktuellen "
        "Abstimmungen kann das Resultat-Feld leer sein ('Ergebnis ausstehend'). "
        "Kantonale Resultate werden nur für nationale Abstimmungen mit "
        "Ständemehr-Erfordernis vollständig geliefert.</important_notes>\n\n"
        "<example>votation_id='v1' | votation_id='2024-09-22-bildung'</example>"
    ),
    annotations={
        "title": "SRG SSR Polis – Abstimmungsresultate",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def srgssr_polis_get_votation_results(params: PolisResultInput) -> str:
    """Ruft detaillierte Resultate einer Schweizer Volksabstimmung ab.
    Liefert Ja/Nein-Anteile, Stimmbeteiligung und kantonale Ergebnisse.
    Benötigt eine votation_id aus srgssr_polis_get_votations.

    Args:
        params (PolisResultInput): Enthält:
            - votation_id (str): Abstimmungs-ID
            - response_format (str): 'markdown' oder 'json'

    Returns:
        str: Detaillierte Abstimmungsresultate mit Ja/Nein-Anteilen und kantonalen Ergebnissen
    """
    log = logger.bind(
        tool="srgssr_polis_get_votation_results",
        votation_id=params.votation_id,
    )
    log.info("tool_invoked")
    try:
        data = await _api_get(f"{POLIS_BASE}/votations/{params.votation_id}")
    except Exception as e:
        log.error("tool_failed", error_type=type(e).__name__, error=str(e))
        return _handle_error(
            e,
            not_found_hint=(
                f"votation_id='{params.votation_id}' nicht gefunden. Verwende "
                f"srgssr_polis_get_votations (optional mit year_from/year_to oder "
                f"canton) und übernimm die ID aus der Resultatliste."
            ),
        )

    log.info("tool_succeeded")

    if params.response_format == ResponseFormat.JSON:
        return json.dumps(data, indent=2, ensure_ascii=False)

    return _format_votation_result(data)


def _format_votation_result(data: dict) -> str:
    title = data.get("title", data.get("titleDe", "Abstimmung"))
    v_date = data.get("date", data.get("votationDate", "?"))
    result = data.get("result", {})

    yes_pct = result.get("yesPercentage", result.get("jaStimmenInProzent", "?"))
    no_pct = result.get("noPercentage", result.get("neinStimmenInProzent", "?"))
    accepted = result.get("accepted", result.get("angenommen", None))
    turnout = result.get("turnout", result.get("stimmbeteiligung", "?"))

    accepted_label = "✅ Angenommen" if accepted else ("❌ Abgelehnt" if accepted is False else "Ergebnis ausstehend")

    lines = [
        f"## {title}\n",
        f"**Datum:** {v_date}",
        f"**Resultat:** {accepted_label}",
        f"**Ja:** {yes_pct}% | **Nein:** {no_pct}%",
        f"**Stimmbeteiligung:** {turnout}%",
    ]

    cantonal = data.get("cantonalResults", data.get("kantonaleResultate", []))
    if cantonal:
        lines.append("\n### Kantonale Resultate")
        for cr in cantonal:
            kanton = cr.get("canton", cr.get("kanton", "?"))
            k_yes = cr.get("yesPercentage", cr.get("jaStimmenInProzent", "?"))
            k_accepted = "✅" if cr.get("accepted", cr.get("angenommen", False)) else "❌"
            lines.append(f"- {k_accepted} **{kanton}**: {k_yes}% Ja")

    return "\n".join(lines)


@mcp.tool(
    name="srgssr_polis_get_elections",
    description=(
        "Ruft Schweizer Nationalrats-, Ständerats- und kantonale Regierungs- bzw. "
        "Parlamentswahlen aus dem Polis-System ab. Liefert Datum, Wahlbezeichnung "
        "und Wahl-ID pro Eintrag.\n\n"
        "<use_case>Historische Wahlanalysen, journalistische Recherchen zu "
        "politischen Mehrheiten, Bildungsmaterial zum Schweizer Wahlsystem, "
        "Trendvergleiche zwischen Wahljahren. Im Unterschied zu "
        "srgssr_polis_get_votations (Sachvorlagen) liefert dieses Tool "
        "Personenwahlen.</use_case>\n\n"
        "<important_notes>Daten reichen zurück bis 1900. Filter nach Jahr "
        "(year_from/year_to) und Kanton möglich; ohne canton-Filter werden "
        "nationale Wahlen geliefert. Liefert ausschliesslich Wahl-Metadaten "
        "(keine Stimmen-Resultate oder Sitzverteilungen). Paginiert mit "
        "page_size 1–100.</important_notes>\n\n"
        "<example>year_from=2023 | canton='ZH', year_from=2015, year_to=2024 | "
        "page_size=50</example>"
    ),
    annotations={
        "title": "SRG SSR Polis – Schweizer Wahlen",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def srgssr_polis_get_elections(params: PolisListInput) -> str:
    """Ruft Schweizer Nationalrats- und Ständeratswahlen sowie Regierungsratswahlen aus dem Polis-System ab.
    Daten reichen zurück bis 1900.

    Args:
        params (PolisListInput): Enthält:
            - year_from (Optional[int]): Startjahr
            - year_to (Optional[int]): Endjahr
            - canton (Optional[str]): Kantonskürzel für kantonale Wahlen
            - page_size (int): Einträge pro Seite
            - page (int): Seitennummer
            - response_format (str): 'markdown' oder 'json'

    Returns:
        str: Liste von Wahlen mit Datum, Bezeichnung und Wahl-ID
    """
    log = logger.bind(
        tool="srgssr_polis_get_elections",
        year_from=params.year_from,
        year_to=params.year_to,
        canton=params.canton.upper() if params.canton else None,
        page=params.page,
        page_size=params.page_size,
    )
    log.info("tool_invoked")
    try:
        query_params: dict = {
            "pageSize": params.page_size,
            "pageNumber": params.page,
        }
        if params.year_from:
            query_params["yearFrom"] = params.year_from
        if params.year_to:
            query_params["yearTo"] = params.year_to
        if params.canton:
            query_params["canton"] = params.canton.upper()

        data = await _api_get(f"{POLIS_BASE}/elections", params=query_params)
    except Exception as e:
        log.error("tool_failed", error_type=type(e).__name__, error=str(e))
        return _handle_error(e)

    elections = data.get("electionList", data.get("elections", []))
    total = data.get("total", len(elections))
    log.info("tool_succeeded", result_count=len(elections), total=total)

    if params.response_format == ResponseFormat.JSON:
        return json.dumps({"total": total, "elections": elections}, indent=2, ensure_ascii=False)

    if not elections:
        suggestions = []
        if params.canton:
            suggestions.append(
                f"canton-Filter entfernen (Wahlen für '{params.canton.upper()}' "
                f"sind möglicherweise nicht erfasst)"
            )
        if params.year_from and params.year_from > 1990:
            suggestions.append(f"year_from auf einen früheren Wert setzen (z.B. {params.year_from - 10})")
        if not suggestions:
            suggestions.append("Filter weglassen, um den vollen Datenbestand seit 1900 zu sehen")
        return (
            "Keine Wahlen gefunden mit den angegebenen Filtern. "
            "Vorschläge: " + "; ".join(suggestions) + "."
        )

    lines = ["## Schweizer Wahlen\n", f"*Total: {total} Wahlen, Seite {params.page}*\n"]
    for el in elections:
        el_date = el.get("date", el.get("electionDate", "?"))
        title = el.get("title", el.get("titleDe", "Unbekannt"))
        el_id = el.get("id", "?")
        lines.append(f"- **{el_date}** — {title} (ID: `{el_id}`)")

    return "\n".join(lines)
