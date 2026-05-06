# Änderungsprotokoll / Changelog

Alle wesentlichen Änderungen werden in dieser Datei dokumentiert.
Das Format basiert auf [Keep a Changelog](https://keepachangelog.com/de/1.0.0/).

## [Unreleased]

## [1.0.0] – 2026-05-06

Erste stabile Release. Sämtliche Findings des `mcp-audit-skill v0.5.0`-Audits
(`audits/2026-05-05T041445-Z-srgssr-mcp/`) sind adressiert; der Server gilt
als production-ready. Diese Release enthält einen **Breaking Change** beim
Wire-Format der Tool-Returns (SDK-002 Option A — siehe unten); Konsumenten
früherer 0.x-Versionen müssen ihre Parsing-Logik anpassen.

### Changed (BREAKING)
- **Tool Returns (SDK-002, Option A):** **BREAKING CHANGE** — alle 15 Tools und beide Resources liefern jetzt typisierte Pydantic-`BaseModel`-Returns statt Markdown- oder JSON-Strings. Konkret:
  - Neues Modul `src/srgssr_mcp/_models.py` mit `ProvenanceFields`-Mixin (source/license/provenance_url/fetched_at) und 16 Response-Models (`WeatherCurrentResponse`, `EpgProgramsResponse`, `VotationsResponse`, `DailyBriefingResponse`, `ToolErrorResponse`, …)
  - Tool-Signaturen: `-> str` → `-> XYZResponse | ToolErrorResponse`. FastMCP exponiert dadurch automatisch ein `outputSchema` pro Tool im `tools/list`-Manifest, das MCP-Clients für präzise Folge-Calls nutzen können.
  - `response_format`-Field wurde aus allen Input-Models entfernt — JSON ist jetzt das einzige Wire-Format. Markdown-Rendering ist die Aufgabe des Konsumenten (LLM-Clients rendern strukturierte JSON-Daten gut).
  - Resources (`epg://{bu}/{channel_id}/{date}`, `votation://{votation_id}`): mime_type wechselt von `text/markdown` zu `application/json`; Inhalt ist die JSON-Serialisierung des entsprechenden Response-Models.
  - Aggregation (`srgssr_daily_briefing`) returnt `DailyBriefingResponse` mit `weather` und `epg` als typisierte Sub-Responses (jede entweder Erfolgs-Response oder `ToolErrorResponse`); die Graceful-Degradation-Garantie bleibt erhalten.
  - **Migration:** Konsumenten, die Markdown-Output erwarteten, müssen entweder (a) auf JSON umstellen (z.B. `result.model_dump()` in Python, JSON-Parser im LLM-Prompt), oder (b) den alten Markdown-Modus aus früheren Versionen pinnen.
  - Adressiert Audit-Findings SDK-002 (medium, FAIL→PASS) und CH-004 (medium, partial→PASS): Provenance ist jetzt strukturell garantiert auf jedem Return-Pfad inkl. Empty-Result und Error-Cases. `_provenance.py` (alter Footer/Envelope-Helper aus PR #31) wurde entfernt; die provenance lebt jetzt in `_models.py`.

### Security
- **Secret Hygiene (ARCH-005):** `Settings.consumer_key` und `Settings.consumer_secret` sind jetzt als `pydantic.SecretStr` typisiert (vorher `str`) und werden in `repr()` / `str()` / Pydantic-Serialisierung als `**********` maskiert — verhindert akzidentelles Klartext-Leak via Logging. `require_credentials()` unwrappt erst am Boundary via `get_secret_value()`. `.gitignore` erweitert um `.env`, `.env.local`, `.env.*.local`, `secrets/`, `credentials/`, `*.pem`, `*.key`. Neu: `.env.example` als kanonisches Template, `.github/workflows/secret-scan.yml` mit gitleaks. Adressiert Audit-Finding ARCH-005 (critical).
- **DNS-Rebinding-Mitigation (SEC-005):** Process-weiter TTL-Cache (5 min) für DNS-Resolutions in `_validate_url_safe`. Auf dem Hot-Path werden subsequente Aufrufe für denselben Hostnamen ohne erneutes `socket.getaddrinfo` bedient; die cached IP hat bereits die SSRF-Blocklist-Prüfung passiert. Single-source-of-truth-Cache zwischen Validation und (potentiell) Connection-Pooling. Reduziert das duplicate-Resolution-TOCTOU-Fenster, das im Audit-Finding SEC-005 (high) als Hauptanliegen geflaggt war. Volle TOCTOU-Eliminierung erfolgt per Layer-2 (Egress-Proxy via Stripe Smokescreen — siehe neue Sektion in `docs/network-egress.md`).
- **Secret Storage Documentation (SEC-013):** Neue Datei `docs/secret-management.md` dokumentiert den aktuellen Stage-1-Reife (Plain Env-Var) inkl. Akzeptanz-Begründung (Public Open Data, single-tenant, read-only) und Eskalations-Triggern auf Stage 3 (managed Secret Manager) bei Cloud-Deployment, Multi-Tenancy, Write-Pfaden oder PII. `lru_cache(maxsize=1)` auf `get_settings()` durch bounded **5-Minuten-TTL-Cache** ersetzt — rotierte Upstream-Credentials werden jetzt innerhalb von 300 s aktiv statt erst beim Process-Restart. Adressiert Audit-Finding SEC-013 (high).
- **Egress-Allowlist-Dokumentation (SEC-021):** Die Code-Layer-Egress-Allowlist (`ALLOWED_HOSTS = {"api.srgssr.ch"}` in `_http.py`, gemeinsam mit SEC-004 SSRF-Defense bereits implementiert) ist jetzt explizit in `README.md` und `README.de.md` als eigener «Security: Egress Allowlist» / «Sicherheit: Egress-Allowlist»-Abschnitt dokumentiert (Allowed Hosts, Erweiterungsprozedur, Pointer auf Tests). Neue Datei `docs/network-egress.md` beschreibt den Network-Layer-Defense-in-Depth-Plan (Kubernetes NetworkPolicy mit FQDN-Egress via Cilium, AWS Security Group, Cloudflare WARP Zero Trust) für zukünftige `sse`/`streamable-http`-Deployments — für den aktuellen `stdio`-Transport nicht anwendbar (Prozess läuft im User-Kontext des MCP-Clients). Neues Audit-Finding `audits/2026-04-30-srgssr-mcp/findings/SEC-021-egress-allowlist.md` dokumentiert den `resolved`-Status mit Test-Matrix.
- **Input Validation Hardening (SEC-018):** Alle 10 Pydantic-Tool-Input-Models (`EpgProgramsInput`, `AudioEpisodesInput`, `PolisListInput`, `PolisResultInput`, `VideoShowsInput`, `VideoEpisodesInput`, `VideoLivestreamsInput`, `WeatherSearchInput`, `WeatherForecastInput`, `DailyBriefingInput`) laufen jetzt im Pydantic-`strict`-Mode (keine implizite Type-Coercion `"5"` → `5`); `extra="forbid"` war bereits vorhanden. Zusätzlich wurden Pattern-Constraints für alle freien String-Felder ergänzt: `channel_id`, `show_id`, `votation_id`, `geolocation_id` akzeptieren nur `^[A-Za-z0-9_-]+$` (blockiert Path-Traversal, URL-Injection, SQL-Metacharacter, Whitespace), `canton` nur `^[A-Za-z]{2,4}$`, `query` (Wettersuche) nur `^[\w\s.\-']+$` (Unicode-aware, blockiert HTML/Script-Payloads). Verteidigt gegen Tool-Boundary-Injection-Angriffe via MCP-Inputs. 23 neue Unit-Tests in `tests/test_unit.py` decken Strict-Mode-Enforcement, Extra-Field-Rejection und alle Pattern-Constraints ab.
- **SSRF Defense (SEC-004 + SEC-021):** Jeder ausgehende HTTP-Request in `_http.py` durchläuft jetzt `_validate_url_safe()` und wird blockiert, wenn (a) das Schema nicht `https` ist, (b) der Hostname nicht in `ALLOWED_HOSTS = {"api.srgssr.ch"}` (Egress-Allowlist) liegt, oder (c) eine der vom Hostname aufgelösten IPs in einer der gesperrten Ranges fällt (RFC1918 privat, Loopback, Link-Local inkl. `169.254.169.254` Cloud-Metadata, CGNAT, Multicast, Reserved sowie die IPv6-Pendants ULA/Link-Local/Loopback/Mapped). Defense-in-Depth gegen DNS-Rebinding und gegen zukünftige Code-Pfade, die URLs aus weniger vertrauenswürdiger Eingabe konstruieren. Aufrufstellen sind `_get_access_token` (OAuth-Token-Endpoint) und `_api_get` (alle Tool-Calls). Verstöße werden als `ValueError` propagiert und durch `_handle_error` zu `Konfigurationsfehler: …` lokalisiert, sodass keine internen Netz-Details an den MCP-Client gelangen. 20 neue Unit-Tests in `tests/test_unit.py` decken HTTPS-Enforcement, Allowlist, alle blockierten IP-Kategorien (inkl. IPv6 und gemischter A/AAAA-Antworten), DNS-Resolver-Fehler und die Integration in `_api_get` / `_safe_api_get` ab.

### Added
- **Lifespan + Connection Pooling (SDK-001):** Neuer `@asynccontextmanager`-Lifespan in `_app.py` ownt einen Process-weit geteilten `httpx.AsyncClient`. `_api_get` und `_get_access_token` nutzen den shared Client (vorher: pro Tool-Call ein neuer `async with httpx.AsyncClient(…)`). Das schaltet HTTP-Connection-Pooling an — kein TCP-Handshake plus TLS-Setup pro Request mehr — und schliesst den Resource-Lifecycle sauber ab beim Server-Shutdown. `asyncio.Lock` schützt erste Client-Erzeugung gegen Race bei `asyncio.gather`-Fan-out, ebenso die initiale OAuth-Token-Refresh-Race. Adressiert Audit-Finding SDK-001 (high, FAIL→PASS) — war der Production-Blocker.
- **Context Injection (SDK-003):** Alle 15 Tools haben jetzt einen optionalen `ctx: Context | None = None`-Parameter. Tools emittieren `await ctx.info(...)` bei Invocation und `srgssr_daily_briefing` zusätzlich `await ctx.report_progress(0/2)` bzw. `(2/2)` um den `asyncio.gather`-Fan-out — MCP-Clients sehen während der Cross-Domain-Aggregation Lebenszeichen. Default ist `None`, daher non-breaking für direkte Funktionsaufrufe (z.B. Tests). Adressiert Audit-Finding SDK-003 (medium, FAIL→PASS).
- **Error Hardening (OBS-001 / OBS-002):** Default-Fallback in `_handle_error()` gibt nicht mehr `str(e)` durch — interne Hostnames, IP-Adressen oder Socket-Details (`gaierror`) bleiben jetzt im strukturierten Server-Log via `logger.error(..., exc_info=e)` und erreichen den LLM-Client nicht mehr. Verhindert Information-Disclosure bei unerwarteten Exceptions. Adressiert Audit-Findings OBS-001 (high) und OBS-002 (high).
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
