"""MCP Prompts (ARCH-008).

Prompts are reusable workflow templates: they stitch together one or more of
the available tools/resources for recurring analysis patterns so users don't
have to phrase the same multi-step request from scratch each time.
"""

from srgssr_mcp._app import mcp


@mcp.prompt(
    name="analyse_abstimmungsverhalten",
    title="Analyse Schweizer Abstimmungsverhalten",
    description=(
        "Strukturierter Workflow zur Analyse einer Schweizer Volksabstimmung: "
        "Stadt-Land-Gefälle, Sprachregionen, kantonale Ausreisser. Nutzt "
        "srgssr_polis_get_votation_results bzw. die Resource votation://<id>."
    ),
)
def analyse_abstimmungsverhalten_prompt(
    votation_id: str,
    focus: str = "stadt_land",
) -> str:
    """Prompt template for analysing voting behaviour for a single votation.

    Args:
        votation_id: ID from srgssr_polis_get_votations.
        focus: 'stadt_land', 'sprachregionen' oder 'kantone' (default 'stadt_land').
    """
    focus_label = {
        "stadt_land": "Stadt-Land-Gefälle (urbane vs. ländliche Kantone)",
        "sprachregionen": "Sprachregionen (Deutschschweiz, Romandie, Tessin, Rätoromanisch)",
        "kantone": "kantonale Ausreisser (Kantone mit deutlich abweichendem Ja-Anteil)",
    }.get(focus, focus)
    return (
        f"Analysiere das Schweizer Abstimmungsverhalten für votation_id='{votation_id}' "
        f"mit Fokus auf {focus_label}.\n\n"
        f"Vorgehen:\n"
        f"1. Lies die Resource `votation://{votation_id}` (oder rufe das Tool "
        f"`srgssr_polis_get_votation_results` mit votation_id='{votation_id}' auf), "
        f"um Ja/Nein-Anteile, Stimmbeteiligung und kantonale Resultate zu erhalten.\n"
        f"2. Fasse das Gesamtresultat zusammen (Annahme/Ablehnung, nationale Ja-Quote, "
        f"Stimmbeteiligung).\n"
        f"3. Identifiziere die drei Kantone mit dem höchsten und tiefsten Ja-Anteil und "
        f"interpretiere sie im Lichte des Fokus '{focus_label}'.\n"
        f"4. Schliesse mit einer kurzen Einordnung: was sagt das Muster über die "
        f"politische Landschaft der Schweiz aus?\n\n"
        f"Bleibe faktenbasiert; kennzeichne Spekulation als solche."
    )


@mcp.prompt(
    name="tagesbriefing_kanton",
    title="Tagesbriefing für einen Schweizer Kanton",
    description=(
        "Workflow für ein Tagesbriefing mit Wetter und TV-/Radio-Programm für eine "
        "Schweizer Stadt. Nutzt srgssr_daily_briefing (oder einzeln "
        "srgssr_weather_forecast_24h + srgssr_epg_get_programs)."
    ),
)
def tagesbriefing_kanton_prompt(
    location: str,
    channel_id: str = "srf1",
    business_unit: str = "srf",
    date: str | None = None,
) -> str:
    """Prompt template for a daily briefing combining weather and EPG.

    Args:
        location: Schweizer Ort oder PLZ (z.B. 'Zürich', '8001', 'Lausanne').
        channel_id: TV-/Radio-Kanal-ID (z.B. 'srf1', 'rts1', 'rsi-la1').
        business_unit: 'srf', 'rts' oder 'rsi'.
        date: ISO-Datum YYYY-MM-DD; leer = heute.
    """
    date_clause = f"das Datum '{date}'" if date else "das heutige Datum"
    return (
        f"Erstelle ein Tagesbriefing für '{location}' und {date_clause}, basierend "
        f"auf SRG-SSR-Daten.\n\n"
        f"Vorgehen:\n"
        f"1. Standort auflösen: Tool `srgssr_weather_search_location` mit "
        f"query='{location}' aufrufen, um Koordinaten und geolocationId zu erhalten.\n"
        f"2. Wetter und Programm parallel via `srgssr_daily_briefing` abfragen "
        f"(business_unit='{business_unit}', channel_id='{channel_id}'); alternativ "
        f"die Resource `epg://{business_unit}/{channel_id}/<date>` lesen und "
        f"`srgssr_weather_forecast_24h` aufrufen.\n"
        f"3. Briefing strukturieren: Wetterüberblick (Temperatur-Range, Niederschlag, "
        f"Wetterlage) → drei Programm-Highlights mit Sendezeit → kurze Empfehlung "
        f"(z.B. «Indoor bei Regen, Outdoor bei Sonne»).\n"
        f"4. Schweizerdeutsche Ortsnamen mit Diakritika schreiben (z.B. Zürich, "
        f"Genève) und Sender-Bezeichnungen in Grossbuchstaben (SRF, RTS, RSI).\n\n"
        f"Halte das Briefing knapp (max. 200 Wörter)."
    )
