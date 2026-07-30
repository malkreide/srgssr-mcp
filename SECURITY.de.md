# 🛡️ Sicherheitsrichtlinie & Sicherheitsstatus

[🇬🇧 English Version](SECURITY.md)

`srgssr-mcp` ist Teil des [Swiss Public Data MCP Portfolios](https://github.com/malkreide)
und wurde gegen den internen MCP-Best-Practice-Audit-Katalog gehärtet. Dieses
Dokument fasst den Sicherheitsstatus zusammen und hält die **akzeptierten
Restrisiken** für jene Kontrollen fest, die bewusst auf der
Portfolio-/Gateway-Ebene statt in diesem einzelnen Server behandelt werden.

## Unterstützte Versionen

| Version | Unterstützt |
|---|---|
| `0.1.x` | ✅ |

Sicherheitsfixes werden gegen die aktuelle `0.1.x`-Linie veröffentlicht. Ältere
Vorab-Builds werden nicht gepflegt.

## Eine Schwachstelle melden

Bitte eröffne ein privates [Security Advisory](https://github.com/malkreide/srgssr-mcp/security/advisories/new)
im GitHub-Repository oder kontaktiere die in [`README.md`](README.md) genannte
Maintainerin. **Melde ausnutzbare Schwachstellen nicht über öffentliche Issues.**

Bitte beim Melden angeben:

- Eine Beschreibung der Schwachstelle und ihrer Auswirkung
- Schritte zur Reproduktion (wenn möglich ein Proof-of-Concept)
- Betroffene Version / betroffener Commit
- Allfällige Vorschläge zur Behebung

Mit einer ersten Bestätigung ist innert weniger Tage zu rechnen. Bestätigte
Probleme werden in [`CHANGELOG.md`](CHANGELOG.md) festgehalten, sobald ein Fix
ausgeliefert wird.

## Statusübersicht

Dies ist ein **Nur-Lese-**, **PII-freier** MCP-Server. Alle Tools stellen
ausschliesslich `GET`-artige Anfragen (über OAuth2 Client Credentials) an die
**SRG SSR Public API V2** (`api.srgssr.ch`); das OAuth2-Token selbst wird vom
Apigee-Runtime-Host `srgssr-prod.apigee.net` bezogen. Bereits umgesetzte
Härtung:

| Bereich | Kontrolle |
|---|---|
| Egress | HTTPS-only Code-Layer-Allowlist auf `api.srgssr.ch` (Daten) und `srgssr-prod.apigee.net` (nur Token-Endpunkt); keine benutzergesteuerten URLs (SEC-004 / SEC-021) — siehe [Egress-Allowlist](README.de.md#egress-allowlist), wo auch steht, warum der zweite Host provisorisch ist |
| SSRF / DNS-Rebinding | Jede aufgelöste IP wird gegen private, Loopback-, Link-Local- (inkl. `169.254.169.254`), CGNAT-, Multicast- und Reserved-Ranges geprüft; eine einzige, TTL-gecachte DNS-Auflösung schliesst das TOCTOU-Fenster (SEC-005) |
| TLS | Zertifikatsprüfung standardmässig aktiv (httpx-Default); nie deaktiviert |
| Binding | Standardmässig stdio-Transport; der optionale HTTP/SSE-Transport bindet über den SDK-Default und wird per expliziter Env-Var (`SRGSSR_MCP_HOST`/`PORT`) gesteuert |
| Eingaben | Strikte Pydantic-v2-Validierung auf jedem Tool-Eingabemodell; Business Units und IDs werden vor jeder Anfrage validiert |
| Tools | Jedes Tool setzt `readOnlyHint: True`; es existieren per Design keine Schreib-, Mutations- oder Löschpfade (Phase 1: Read-only Wrapper) |
| Secrets | `SRGSSR_CONSUMER_KEY` / `SRGSSR_CONSUMER_SECRET` sind als `pydantic.SecretStr` typisiert — nie in `repr()` oder Logs sichtbar (ARCH-005); `.env*` und `secrets/` sind git-ignoriert; ein `gitleaks`-Secret-Scan-Workflow läuft bei jedem Push |
| Secret-Management | Stufe-1-Speicherung (Plain Env-Var) mit dokumentierter Akzeptanz-Begründung und Eskalations-Triggern — siehe [`docs/secret-management.md`](docs/secret-management.md) (SEC-013) |
| Fehler | Upstream-Fehlerbodies und Stacktraces werden nur nach stderr geloggt; das Modell erhält eine generische, nicht-leckende Meldung (OBS-002) |
| Stdout | Reserviert für den JSON-RPC-Stream; sämtliches strukturiertes Logging auf stderr gepinnt (OBS-003) |
| Resilienz | Ein 30s-Timeout pro Anfrage begrenzt jeden Upstream-Aufruf |

Die Härtungshistorie steht in [`CHANGELOG.md`](CHANGELOG.md), die zugrunde
liegenden Audit-Reports und Findings im Verzeichnis [`audits/`](audits/).

## Akzeptierte Restrisiken (Kontrollen auf Portfolio-Ebene)

Die folgenden Audit-Checks sind bewusst **nicht** innerhalb dieses Servers
umgesetzt. Es handelt sich um portfolioweite Belange, die am besten auf einer
MCP-Gateway-/Host-Ebene durchgesetzt werden; das Restrisiko ist hier gering,
weil der Server nur lesend arbeitet und nur einen einzigen vertrauenswürdigen
Public-Data-Anbieter erreicht.

### SEC-014 — Tool-Allow-Listing über ein MCP-Gateway

**Status:** akzeptiertes Risiko (Portfolio-Ebene).
Eine Tool-bezogene Allow-List gehört zum MCP-Host/-Gateway, das mehrere Server
aggregiert, nicht zu einem einzelnen Server mit festem, nur lesendem Tool-Set.
Sobald ein zentrales Gateway für das Portfolio eingeführt wird, sollte das
Tool-Allow-Listing dort konfiguriert werden. Bis dahin ist das Risiko begrenzt:
Jedes Tool ist nur lesend und auf den obigen festen Endpunkt beschränkt.

### SEC-015 — Pre-Flight-Erkennung von Tool-Poisoning

**Status:** akzeptiertes Risiko (Portfolio-Ebene) — mit lokaler Absicherung.
Tool-Poisoning (bösartige Tool-Beschreibungen / Rug-Pulls) ist ein
Supply-Chain- und Host-seitiges Thema. Die Tool-Definitionen dieses Servers
sind versionskontrolliert, im Repo verfasst und via PR reviewt; es gibt keine
dynamische oder entfernte Tool-Registrierung. Server-übergreifende
Poisoning-Erkennung bleibt eine Gateway-/Host-Verantwortung auf Portfolio-Ebene.

## Trigger für eine Neubewertung

Diese Akzeptanzen sollten neu bewertet werden, falls der Server jemals:

- **Schreib**-Fähigkeit erhält oder **PII** verarbeitet, oder
- ein **Authentifizierungs**-Modell für Endnutzende erhält (dann gebundene,
  TTL-versehene, serverseitig invalidierbare Session-IDs implementieren und vor
  dem Merge neu auditieren), oder
- als langlebiger HTTP/SSE-Dienst in die **Cloud** deployed wird (dann die
  Secret-Speicherung gemäss [`docs/secret-management.md`](docs/secret-management.md)
  auf einen verwalteten Secret Manager eskalieren und die Netzwerk-Layer-Egress-
  Kontrollen aus [`docs/network-egress.md`](docs/network-egress.md) anwenden), oder
- Tools **dynamisch** / aus entfernten Quellen registriert, oder
- hinter einem gemeinsamen MCP-Gateway aggregiert wird (dann das
  Tool-Allow-Listing und die Tool-Poisoning-Erkennung des Gateways aktivieren).
