# Änderungsprotokoll / Changelog

Alle wesentlichen Änderungen werden in dieser Datei dokumentiert.
Das Format basiert auf [Keep a Changelog](https://keepachangelog.com/de/1.0.0/).

## [Unreleased]

### Added
- **Docs (OPS-003):** Neue README-Sektion «Development Phase» / «Entwicklungsphase» (EN/DE) deklariert den Server explizit als **Phase 1: Read-only Wrapper** und listet die Phase-1-Abschlusskriterien als Checkliste (14 Tools, OAuth2, bilinguale Doku, Test-Suite via OPS-001, Structured Logging via OBS-003; ausstehend: Production-ready Error-Handling). Phase 2 (Write) ist als *nicht geplant* markiert — die SRG SSR APIs sind per Vertrag read-only. Phase 3 (Multi-Agent) wird auf User-Feedback-getriebene Re-Evaluation aufgeschoben.
- **Observability (OBS-003):** Structured logging via `structlog` mit JSON-Output auf stderr und RFC-5424-Severity-Stufen (debug/info/notice/warning/error/critical/alert/emergency). Jeder Tool-/Resource-Aufruf bindet Kontext (`tool`, `business_unit`, `channel_id`, `query`, …) und emittiert `tool_invoked`/`tool_succeeded`/`tool_failed`-Events; OAuth-Token-Refresh und Server-Lifecycle werden ebenfalls geloggt. Stdio-Transport bleibt sauber (stdout für JSON-RPC, Logs auf stderr). Konfiguration via `SRGSSR_LOG_LEVEL` (Default `info`). Neue `tests/test_logging.py` mit 9 Tests; neue Dependency `structlog>=24.1.0`.

### Changed
- **Architecture (ARCH-012):** **MCP `protocolVersion` pinned to `2025-06-18`** (vorher SDK-Default). Die Spec-Version ist als `PROTOCOL_VERSION`-Konstante in `src/srgssr_mcp/_app.py` explizit verankert und wird beim Import gegen die `SUPPORTED_PROTOCOL_VERSIONS` des installierten MCP-SDK validiert — ein SDK-Upgrade, das die gepinnte Spec-Revision nicht mehr unterstützt, schlägt sofort beim Start fehl statt still die Wire-Semantik zu ändern. README erhält eine «MCP Protocol Version»-Sektion mit Update-Policy; Dependabot wartet die `mcp`/`fastmcp`-Dependencies monatlich.
- **Architecture (ARCH-011):** `server.py` (~1900 Zeilen) wurde in fokussierte Module aufgeteilt: `config.py` (Settings), `_http.py` (OAuth/HTTP-Plumbing), `_app.py` (FastMCP-Instanz + Enums) sowie `tools/{weather,video,audio,epg,polis,aggregation,resources,prompts}.py` mit jeweils einem Tool-Cluster. `server.py` ist jetzt ein dünner Entry-Point, der die Tool-Module zur Registrierung importiert und alle bestehenden Symbole für Rückwärtskompatibilität re-exportiert. Public API (`from srgssr_mcp.server import …`) bleibt unverändert; alle 78 Unit-Tests passieren weiter.

### Added
- **Architecture (ARCH-008):** Server nutzt jetzt alle drei MCP-Primitive. Neue **Resources** mit URI-Templates für stabile, cache-freundliche Daten: `epg://{bu}/{channel_id}/{date}` für EPG-Tagesprogramme (SRF/RTS/RSI) und `votation://{votation_id}` für abgeschlossene Schweizer Volksabstimmungen. Neue **Prompts** für wiederkehrende Workflows: `analyse_abstimmungsverhalten` (Stadt-Land/Sprachregionen/Kantone-Fokus) und `tagesbriefing_kanton` (Wetter + EPG für eine Stadt). Tools bleiben für parametrisierte Suchen erhalten.

### Changed
- **Architecture (ARCH-004):** Konfiguration wurde auf Pydantic `BaseSettings` umgestellt (`srgssr_mcp.server.Settings`). Credentials und Transport (`stdio` / `sse` / `streamable-http`) werden zentral aus Environment-Variablen gelesen (`SRGSSR_CONSUMER_KEY`, `SRGSSR_CONSUMER_SECRET`, `SRGSSR_MCP_TRANSPORT`, `SRGSSR_MCP_HOST`, `SRGSSR_MCP_PORT`, `SRGSSR_MCP_MOUNT_PATH`). `main()` wählt den Transport zur Laufzeit; Tools bleiben transport-agnostisch.
- **UX (ARCH-003):** `srgssr_weather_search_location` führt bei leerem Resultat automatische Retries mit normalisierten Query-Varianten (ASCII-gefaltet, lowercase) aus — «Zurich» trifft jetzt «Zürich». Bei finaler Leere werden versuchte Varianten und Suggestions (PLZ, Diakritika) zurückgegeben.
- **UX (ARCH-003):** 404-Antworten in ID-Lookup-Tools (`srgssr_video_get_episodes`, `srgssr_audio_get_episodes`, `srgssr_polis_get_votation_results`, `srgssr_epg_get_programs`) verweisen jetzt auf das passende Listing-Tool zur ID-Auflösung.
- **UX (ARCH-003):** Listen-Tools (`srgssr_video_get_shows`, `srgssr_audio_get_shows`, beide Livestream-Tools, `srgssr_polis_get_votations`, `srgssr_polis_get_elections`) liefern bei leerem Resultat strukturierte Vorschläge (alternative Business Units, Filter lockern).
- **Docs (OPS-002):** Architecture-Diagramm in README.md/README.de.md auf Tool-Cluster-Layout (Weather/EPG/Polis/Video/Audio) umgestellt
- **Docs (OPS-002):** «Known Limits» / «Bekannte Limits» Sektion ergänzt um Rate Limits, Data Freshness (EPG ≤ 6h Verzögerung), Historical Data (Polis ab 1900) und Geo-Restriction

## [0.1.0] - 2026-03-29

### Added
- Initial release
- 12 Tools für SRG SSR APIs: SRF Wetter (4), Video (3), Audio (3), EPG (1), Polis/Demokratie (3)
- Unterstützung für SRF, RTS, RSI, RTR, SWI
- Historische Abstimmungs- und Wahldaten seit 1900 via Polis-API
- OAuth2-Authentifizierung für SRG SSR Developer APIs
- Dual-Transport: stdio (lokal) + Streamable HTTP (Cloud)

## [0.1.0] – 2026-03-29

### Neu
- **14 Tools** in 5 thematischen Clustern
- **Wetter (4):** `srgssr_weather_search_location`, `srgssr_weather_current`, `srgssr_weather_forecast_24h`, `srgssr_weather_forecast_7day`
- **Video (3):** `srgssr_video_get_shows`, `srgssr_video_get_episodes`, `srgssr_video_get_livestreams`
- **Audio (3):** `srgssr_audio_get_shows`, `srgssr_audio_get_episodes`, `srgssr_audio_get_livestreams`
- **EPG (1):** `srgssr_epg_get_programs`
- **Polis (3):** `srgssr_polis_get_votations`, `srgssr_polis_get_votation_results`, `srgssr_polis_get_elections`
- Unterstützung für alle SRG SSR Unternehmenseinheiten: SRF, RTS, RSI, RTR, SWI
- Historische Abstimmungs- und Wahldaten seit 1900 via Polis-API
- OAuth2 Client Credentials mit automatischem Token-Caching
- Duale Transport-Unterstützung: stdio (lokal) und Streamable HTTP (Cloud)
- Paginierungsunterstützung für alle Listen-Tools
- GitHub Actions CI für Python 3.11–3.13
- Bilinguales README (DE/EN) und CONTRIBUTING (DE/EN)

### Quellen
- SRG SSR PUBLIC API V2 via [developer.srgssr.ch](https://developer.srgssr.ch)
