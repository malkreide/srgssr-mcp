# Finding: SEC-021 — Egress-Allow-List: Code-Layer und Network-Layer

| Feld | Wert |
|---|---|
| **Severity** | high |
| **Status** | resolved |
| **Server** | `srgssr-mcp` |
| **Check-Reference** | `SEC-021` |
| **PDF-Reference** | Anhang B5 + B12 |
| **Audit-Datum** | 2026-04-30 |
| **Auditor** | Claude (mcp-audit-skill v0.5.0) |

## Observed Behavior (vor Fix)

Die automatisierte Audit-Heuristik (`grep -rE 'allowed_(domains|hosts|origins)|domain_allowlist|host_whitelist'`) hat keine Egress-Allowlist gefunden, weil im Server eine alternative Benennung (`ALLOWED_HOSTS` / `_validate_url_safe`) verwendet wurde. Tatsächlich war die Code-Layer-Allowlist zum Zeitpunkt des Audits bereits gemeinsam mit SEC-004 in `src/srgssr_mcp/_http.py` implementiert; das Finding wurde geöffnet, um die Lücke zwischen Auditregex und tatsächlichem Code zu schließen sowie die Dokumentation auf Code-Ebene und in der README explizit zu machen.

## Expected Behavior

Defense-in-Depth verlangt zwei Layer für Egress-Control:

1. **Code-Layer Allow-List** — vor jedem ausgehenden HTTP-Request wird die Ziel-Domain gegen ein hartes Allowlist-Set geprüft.
2. **Network-Layer Egress Control** — für Production-Deployments (SSE/HTTP-Transport) zusätzlich auf Infrastruktur-Ebene (Kubernetes NetworkPolicy, AWS Security Groups, Cloudflare WARP).

Für den aktuellen `stdio`-Deployment-Modus ist Layer 2 nicht anwendbar, aber dokumentierungswürdig für den Fall eines zukünftigen SSE/HTTP-Deployments.

## Remediation

### Status: implementiert (Code-Layer) + dokumentiert (Network-Layer)

**1. Code-Layer Allow-List — `src/srgssr_mcp/_http.py`**

Die Egress-Allowlist ist als unveränderliches `frozenset` definiert und wird durch `_validate_url_safe()` vor jedem `httpx`-Aufruf erzwungen — mit drei kombinierten Kontrollen (HTTPS-only, Host-Allowlist, IP-Blocklist; siehe SEC-004 für IP-Blocklist-Details):

```python
ALLOWED_HOSTS: frozenset[str] = frozenset({"api.srgssr.ch"})

def _validate_url_safe(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError("SSRF blocked: only HTTPS is permitted ...")
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("SSRF blocked: URL has no hostname")
    if hostname not in ALLOWED_HOSTS:
        raise ValueError(
            f"SSRF blocked: host '{hostname}' is not in the egress allowlist "
            f"({sorted(ALLOWED_HOSTS)})"
        )
    # ...IP-Blocklist (SEC-004)...
```

**Begründung der strikten Allowlist:**

Das Audit-Beispiel schlägt eine breitere Liste mit Subdomain-Wildcard vor (`srgssr.ch`, `*.srgssr.ch`, …). Die tatsächliche Code-Surface verwendet hingegen nur einen einzigen Host (`api.srgssr.ch`, in `_http.py:17` als `BASE_URL` hard-coded; alle Sub-URLs `WEATHER_BASE`, `VIDEO_BASE`, `AUDIO_BASE`, `EPG_BASE`, `POLIS_BASE`, `TOKEN_URL` hängen daran). Eine exakte Match-Allowlist ist daher **strikter und sicherer** als eine Subdomain-Wildcard-Variante:

- Subdomain-Trick `api.srgssr.ch.evil.example` wird durch Exact-Match abgefangen (Test: `test_validate_url_safe_rejects_attacker_controlled_subdomain`).
- Eine zukünftige versehentliche Erweiterung um eine andere Subdomain (`malicious.srgssr.ch`) erfordert eine bewusste Allowlist-Änderung im Code-Review — sie passiert nicht stillschweigend.

**Aufrufstellen — alle ausgehenden HTTP-Requests sind abgesichert:**

- `_get_access_token()` validiert `TOKEN_URL` vor dem OAuth-POST (`_http.py:120`).
- `_api_get(url)` validiert die übergebene URL vor jedem GET (`_http.py:144`).
- `_safe_api_get` ruft `_api_get` und mappt den `ValueError` über `_handle_error` auf eine lokalisierte `Konfigurationsfehler: …`-Meldung — interne Netz-Details werden nicht an den MCP-Client geleakt.
- Es gibt **keinen** weiteren `httpx.AsyncClient`-Call-Pfad im Server (verifiziert via `grep -rn 'httpx\.' src/`).

**2. Network-Layer Egress Control — Dokumentation für zukünftige Deployments**

Da der Server aktuell ausschliesslich via `stdio` betrieben wird, ist eine Netzwerk-Layer-Egress-Kontrolle nicht anwendbar (es gibt keinen Pod / keine Security-Group, die den Prozess umschliesst — der Prozess läuft im User-Kontext des MCP-Clients, z.B. Claude Desktop). Für zukünftige `sse`/`streamable-http`-Deployments ist `docs/network-egress.md` als Referenz hinterlegt (Kubernetes NetworkPolicy, AWS Security Group, Cloudflare WARP).

**3. Dokumentation**

- `README.md` und `README.de.md` haben einen neuen Abschnitt **«Security: Egress Allowlist»** / **«Sicherheit: Egress-Allowlist»**, der Allowed Hosts, Erweiterungsprozedur und Tests-Pointer beschreibt.
- `CHANGELOG.md` referenziert SEC-021 unter `[Unreleased] → Security`.
- `docs/network-egress.md` liefert den Network-Layer-Defense-in-Depth-Plan für zukünftige Deployments.

## Effort Estimate

**M** — kombiniert mit SEC-004 implementiert.

## Verification After Fix

Status: **resolved** — Akzeptanzkriterien erfüllt.

```bash
# Code-Check: Allowlist und Validation präsent
$ grep -nE 'ALLOWED_HOSTS|_validate_url_safe' src/srgssr_mcp/_http.py
34:ALLOWED_HOSTS: frozenset[str] = frozenset({"api.srgssr.ch"})
60:def _validate_url_safe(url: str) -> None:
85:    if hostname not in ALLOWED_HOSTS:
120:    _validate_url_safe(TOKEN_URL)
144:    _validate_url_safe(url)

# Test-Check: 21 SSRF/Allowlist-Tests grün
$ PYTHONPATH=src python -m pytest tests/test_unit.py -k "ssrf or validate_url or api_get_blocks or all_base_urls or token_url or maps_ssrf" -v
21 passed in 0.21s

# Re-Run: Egress-Heuristik findet jetzt die Implementierung
$ grep -rE 'ALLOWED_HOSTS|_validate_url_safe' src/
# (Treffer in _http.py und server.py-Re-Export)
```

**Test-Abdeckung der Allowlist-Kontrolle (SEC-021-spezifisch):**

| Test | Verifiziert |
|---|---|
| `test_validate_url_safe_rejects_host_outside_allowlist` | Fremder Host (`evil.example.com`) → `PermissionError`/`ValueError` |
| `test_validate_url_safe_rejects_attacker_controlled_subdomain` | Subdomain-Suffix-Trick (`api.srgssr.ch.evil.example`) abgefangen |
| `test_validate_url_safe_accepts_public_srgssr_host` | `api.srgssr.ch` wird durchgelassen |
| `test_api_get_blocks_disallowed_host` | Integration: `_api_get` blockiert nicht-allowlisted Host |
| `test_safe_api_get_returns_localized_message_on_ssrf_block` | Fehler wird zu lokalisierter `Konfigurationsfehler:`-Meldung gemappt |
| `test_token_url_is_https_and_in_allowlist` | OAuth-Token-Endpoint erfüllt selbst die Policy |
| `test_all_base_urls_are_https_and_in_allowlist` | Alle hard-coded Base-URLs erfüllen die Policy |
