# Use Cases & Examples — srgssr-mcp

Real-world queries by audience. Indicate per example whether an API key is required.

🏫 **Bildung & Schule**
Lehrpersonen, Schulbehörden, Fachreferent:innen

**Historische Entwicklung der Frauenstimmrechts-Abstimmungen**
«Welche Abstimmungen gab es auf nationaler Ebene zum Thema Frauenstimmrecht zwischen 1950 und 1971 und wie sahen die kantonalen Resultate der finalen Abstimmung 1971 aus?»
→ `srgssr_polis_get_votations(year_from=1950, year_to=1971)`
→ `srgssr_polis_get_votation_results(votation_id="xxxx")` *(API Key erforderlich)*
Warum nützlich: Ermöglicht Geschichtslehrpersonen, historische Abstimmungen mit detaillierten echten Daten (inklusive Röstigraben-Analyse) direkt im Unterricht aufzubereiten.

**Wetterdaten für Schulreisen**
«Wie wird das Wetter morgen in Luzern, und gibt es ein Regenrisiko für unseren Ausflug?»
→ `srgssr_weather_search_location(query="Luzern")` *(API Key erforderlich)*
→ `srgssr_weather_forecast_24h(latitude=47.0502, longitude=8.3093)` *(API Key erforderlich)*
Warum nützlich: Hilft Lehrkräften, wetterabhängige Exkursionen zuverlässig mit lokalen Schweizer Wetterdaten von SRF Meteo zu planen.

👨‍👩‍👧 **Eltern & Schulgemeinde**
Elternräte, interessierte Erziehungsberechtigte

**Familienprogramm am Wochenende**
«Was für familienfreundliche Sendungen laufen diesen Samstagmorgen auf SRF 1?»
→ `srgssr_epg_get_programs(business_unit="srf", channel_id="srf1", date="2024-05-18")` *(API Key erforderlich)*
Warum nützlich: Bietet Eltern einen schnellen Überblick über das Fernsehprogramm des Wochenendes, ohne sich durch verschiedene TV-Zeitschriften suchen zu müssen.

**Abstimmungen zu Familienpolitik**
«Wie hat mein Kanton (Aargau) bei den letzten Abstimmungen zu Vaterschaftsurlaub und Kinderbetreuung abgestimmt?»
→ `srgssr_polis_get_votations(canton="AG", year_from=2015)` *(API Key erforderlich)*
→ `srgssr_polis_get_votation_results(votation_id="xxxx")` *(API Key erforderlich)*
Warum nützlich: Erlaubt es Elternräten, die lokale politische Stimmungssituation bezüglich familienspezifischer Vorlagen nachzuvollziehen.

🗳️ **Bevölkerung & öffentliches Interesse**
Allgemeine Öffentlichkeit, politisch und gesellschaftlich Interessierte

**Informationen zu kommenden Abstimmungen**
«Gibt es aktuelle SRF-Sendungen oder Debatten, die sich mit der kommenden BVG-Reform befassen?»
→ `srgssr_video_get_shows(business_unit="srf")` *(API Key erforderlich)*
→ `srgssr_video_get_episodes(business_unit="srf", show_id="srf-arena")` *(API Key erforderlich)*
Warum nützlich: Hilft Stimmbürger:innen, sich durch aktuelle politische Diskussionssendungen der SRG ausgewogen auf Urnengänge vorzubereiten.

**Lokale Wetterwarnungen und Prognosen**
«Wie entwickelt sich das Wetter in den nächsten 7 Tagen in meinem Wohnort Davos?»
→ `srgssr_weather_search_location(query="Davos")` *(API Key erforderlich)*
→ `srgssr_weather_forecast_7day(latitude=46.8043, longitude=9.832)` *(API Key erforderlich)*
Warum nützlich: Bietet Bürger:innen präzise mittelfristige Wetterprognosen für alpine Regionen, wo das Wetter schnell umschlagen kann.

**Kantonale Abstimmungsgeschichte**
«Welche Volksabstimmungen fanden zwischen 2010 und 2020 im Kanton Bern statt?»
→ `srgssr_polis_get_votations(canton="BE", year_from=2010, year_to=2020)` *(API Key erforderlich)*
Warum nützlich: Stärkt das staatsbürgerliche Verständnis, indem es Bürger:innen ermöglicht, die politische Geschichte ihres eigenen Kantons leicht zu erkunden.

🤖 **KI-Interessierte & Entwickler:innen**
MCP-Enthusiast:innen, Forscher:innen, Prompt Engineers, öffentliche Verwaltung

**Demokratie-Synergien (Multi-Server)**
«Zeige mir die kantonalen Resultate der Konzernverantwortungsinitiative und vergleiche die Stimmbeteiligung mit dem nationalen Durchschnitt jener Zeit.»
→ `srgssr_polis_get_votation_results(votation_id="6360")` *(API Key erforderlich)*
→ `bfs_get_dataset(dataset_id="px-x-1703030000_100")` (via [swiss-statistics-mcp](https://github.com/malkreide/swiss-statistics-mcp))
Warum nützlich: Demonstriert die Leistungsfähigkeit von MCP, indem historische Abstimmungsresultate der SRG mit detaillierten demografischen Daten des BFS verknüpft werden.

**Automatisierte Programm-Kuratierung**
«Liste alle aktuellen Episoden des SRF 'Echo der Zeit' auf und fasse die Hauptthemen der Woche zusammen.»
→ `srgssr_audio_get_shows(business_unit="srf")` *(API Key erforderlich)*
→ `srgssr_audio_get_episodes(business_unit="srf", show_id="srf-echo-der-zeit")` *(API Key erforderlich)*
Warum nützlich: Erlaubt Entwickler:innen den Bau von personalisierten Nachrichten-Aggregatoren, die auf verlässlichen SRG-Audioquellen basieren.

🔧 **Technische Referenz: Tool-Auswahl nach Anwendungsfall**

| Ich möchte… | Tool(s) | Auth nötig? |
|---|---|---|
| mich über kommende Abstimmungsresultate informieren | `srgssr_polis_get_votations`, `srgssr_polis_get_votation_results` | Ja (API Key) |
| das aktuelle und künftige Wetter an meinem Wohnort prüfen | `srgssr_weather_search_location`, `srgssr_weather_forecast_7day` | Ja (API Key) |
| das TV-Programm eines bestimmten Tages abfragen | `srgssr_epg_get_programs` | Ja (API Key) |
| verpasste Radio- oder TV-Sendungen nachhören oder nachschauen | `srgssr_audio_get_episodes`, `srgssr_video_get_episodes` | Ja (API Key) |
| historische Wahlen in meinem Kanton analysieren | `srgssr_polis_get_elections` | Ja (API Key) |
