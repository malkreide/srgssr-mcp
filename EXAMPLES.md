# Use Cases & Examples — srgssr-mcp

Reale Suchanfragen und Anwendungsfälle nach Zielgruppe.  
**Hinweis:** Alle Tools in diesem Server erfordern zwingend einen API-Key (`SRGSSR_CONSUMER_KEY` und `SRGSSR_CONSUMER_SECRET` von developer.srgssr.ch).

### 🏫 Bildung & Schule
Lehrpersonen, Schulbehörden, Fachreferent:innen

**Historische Analyse von Volksabstimmungen**
«Zeige mir alle eidgenössischen Abstimmungen aus dem Jahr 1971 und rufe danach die kantonalen Resultate zur Einführung des Frauenstimmrechts ab, damit wir diese im Geschichtsunterricht besprechen können.»
→ `srgssr_polis_get_votations(year_from=1971, year_to=1971)`
→ `srgssr_polis_get_votation_results(votation_id="2240")`
**Warum nützlich:** Ermöglicht es Lehrpersonen, den Schülerinnen und Schülern historische politische Entscheide der Schweiz mit echten, unverfälschten Daten direkt im Klassenzimmer aufzuzeigen.

**Medienkompetenz und aktuelle Nachrichten**
«Suche nach den neuesten Episoden der 'Tagesschau' von SRF, um aktuelle Nachrichtenthemen für die Klassenstunde vorzubereiten.»
→ `srgssr_video_get_episodes(business_unit="srf", show_id="srf-tagesschau")`
**Warum nützlich:** Erleichtert Lehrkräften den schnellen Zugriff auf qualitativ hochstehende, verifizierte tagesaktuelle Videoinhalte des Service Public für die Medienbildung.

### 👨‍👩‍👧 Eltern & Schulgemeinde
Elternräte, interessierte Erziehungsberechtigte

**Planung von Schulausflügen und Familienaktivitäten**
«Suche nach dem Standort 'Luzern' und gib mir die genaue 7-Tages-Wetterprognose, damit wir entscheiden können, ob der geplante Familienausflug ins Verkehrshaus stattfinden kann.»
→ `srgssr_weather_search_location(query="Luzern")`
→ `srgssr_weather_forecast_7day(latitude=47.0502, longitude=8.3093, geolocation_id="...")`
**Warum nützlich:** Hilft Eltern und Schulbehörden bei der sicheren und wetterabhängigen Planung von Outdoor-Aktivitäten mit verlässlichen Daten von SRF Meteo.

**Altersgerechtes TV-Programm finden**
«Was läuft heute Nachmittag auf dem Fernsehsender SRF 1? Gibt es familienfreundliche Sendungen?»
→ `srgssr_epg_get_programs(business_unit="srf", channel_id="srf1", date="2024-05-15")`
**Warum nützlich:** Bietet Eltern eine rasche Übersicht des tagesaktuellen Programms, um gezielt passende und werbefreie Inhalte für ihre Kinder auszuwählen.

### 🗳️ Bevölkerung & öffentliches Interesse
Allgemeine Öffentlichkeit, politisch und gesellschaftlich Interessierte

**Kantonale Abstimmungsresultate analysieren**
«Wie hat der Kanton Bern bei den eidgenössischen Abstimmungen im Jahr 2023 im Vergleich zum restlichen Land abgestimmt?»
→ `srgssr_polis_get_votations(year_from=2023, year_to=2023, canton="BE")`
→ `srgssr_polis_get_votation_results(votation_id="6610")`
**Warum nützlich:** Stärkt die politische Transparenz, indem Bürgerinnen und Bürger das kantonale Abstimmungsverhalten detailliert nachvollziehen und auswerten können.

**Zugriff auf regionale Nachrichten im Radio**
«Welche regionalen Radiosendungen laufen aktuell bei Radio Télévision Suisse (RTS) und was sind die neuesten Audio-Episoden des Regionaljournals?»
→ `srgssr_audio_get_shows(business_unit="rts")`
→ `srgssr_audio_get_episodes(business_unit="rts", show_id="rts-info")`
**Warum nützlich:** Verbindet die Bevölkerung direkt mit vertrauenswürdigen, regionalen Audio-Informationen und fördert die gesellschaftliche Teilhabe über Sprachgrenzen hinweg.

### 🤖 KI-Interessierte & Entwickler:innen
MCP-Enthusiast:innen, Forscher:innen, Prompt Engineers, öffentliche Verwaltung

**Demografische Wahlforschung (Multi-Server)**
«Rufe die kantonalen Resultate der AHV-Abstimmung von 2024 aus dem Polis-System der SRG ab und vergleiche diese anschliessend mit der kantonalen Altersstruktur aus dem BFS-Statistik-Server, um Zusammenhänge zwischen Demografie und Abstimmungsverhalten zu analysieren.»
→ `srgssr_polis_get_votations(year_from=2024, year_to=2024)` (via `srgssr-mcp`)
→ `srgssr_polis_get_votation_results(votation_id="6650")` (via `srgssr-mcp`)
→ `bfs_get_dataset(dataset_number="px-x-0102020000_101")` (via [`swiss-statistics-mcp`](https://github.com/malkreide/swiss-statistics-mcp))
**Warum nützlich:** Demonstriert die enorme Analysekraft des MCP-Ökosystems, wenn hochqualitative Abstimmungsdaten der SRG mit detaillierten demografischen Strukturdaten des Bundesamts für Statistik kombiniert werden.

**Automatisierte Erstellung von Programmübersichten**
«Lade die Liste aller Live-Livestreams von SRF und RTS herunter und frage dann das tagesaktuelle EPG-Programm für die beiden Hauptsender ab, um ein kompaktes Markdown-Dashboard zu generieren.»
→ `srgssr_video_get_livestreams(business_unit="srf")`
→ `srgssr_video_get_livestreams(business_unit="rts")`
→ `srgssr_epg_get_programs(business_unit="srf", channel_id="srf1", date="2024-05-15")`
→ `srgssr_epg_get_programs(business_unit="rts", channel_id="rts1", date="2024-05-15")`
**Warum nützlich:** Zeigt Entwicklerinnen und Entwicklern, wie sie mit wenigen API-Aufrufen cross-mediale und mehrsprachige Programmübersichten für eigene Dashboards oder Smarthome-Displays aggregieren können.

### 🔧 Technische Referenz: Tool-Auswahl nach Anwendungsfall

| Ich möchte… | Tool(s) | Auth nötig? |
| :--- | :--- | :--- |
| aktuelle Wetterbedingungen oder Prognosen abrufen | `srgssr_weather_current`, `srgssr_weather_forecast_24h`, `srgssr_weather_forecast_7day` | Ja |
| nach TV-Sendungen und Video-Episoden suchen | `srgssr_video_get_shows`, `srgssr_video_get_episodes` | Ja |
| die Live-TV-Kanäle eines SRG-Senders finden | `srgssr_video_get_livestreams` | Ja |
| Radiosendungen und Audio-Inhalte durchsuchen | `srgssr_audio_get_shows`, `srgssr_audio_get_episodes` | Ja |
| das TV- oder Radioprogramm eines bestimmten Tages ansehen | `srgssr_epg_get_programs` | Ja |
| historische Abstimmungs- oder Wahlresultate abfragen | `srgssr_polis_get_votations`, `srgssr_polis_get_elections` | Ja |
| kantonale Detailergebnisse einer spezifischen Abstimmung ansehen | `srgssr_polis_get_votation_results` | Ja |
