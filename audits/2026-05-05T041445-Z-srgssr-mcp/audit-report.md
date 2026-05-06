# MCP-Server Audit-Report — `srgssr-mcp`

**Audit-Datum:** 2026-05-06
**Skill-Version:** 0.9.x
**Catalog-Version:** v0.5.0 (68 checks)

---

## 1. Executive Summary

Server `srgssr-mcp` wurde gegen 36 anwendbare Best-Practice-Checks geprüft. 23 bestanden, 9 Findings dokumentiert (1 critical, 5 high, 3 medium, 0 low). Production-Readiness: NICHT erreicht — blockierend: SDK-001, SEC-005.

**Production-Readiness:** NO

---

## 2. Profil-Snapshot

| Feld | Wert |
|---|---|
| Server-Name | `srgssr-mcp` |
| Audit-Datum | 2026-05-06 |
| Skill-Version | 0.9.x |
| Catalog-Version | v0.5.0 (68 checks) |
| transport | `dual` |
| auth_model | `none` |
| data_class | `Public Open Data` |
| write_capable | `False` |
| deployment | `['local-stdio', 'Kubernetes']` |
| uses_sampling | `False` |
| tools_make_external_requests | `True` |
| stadt_zuerich_context | `False` |
| schulamt_context | `False` |
| data_source.is_swiss_open_data | `True` |

---

## 3. Applicability

### Status pro Kategorie

| Kategorie | Pass | Fail | Partial | Todo | N/A |
|---|---|---|---|---|---|
| ARCH | 10 | 0 | 1 | 0 | 1 |
| CH | 0 | 0 | 1 | 0 | 7 |
| HITL | 0 | 0 | 0 | 0 | 5 |
| OBS | 2 | 0 | 2 | 0 | 2 |
| OPS | 3 | 0 | 0 | 0 | 0 |
| SCALE | 0 | 0 | 0 | 1 | 5 |
| SDK | 0 | 2 | 1 | 1 | 1 |
| SEC | 8 | 1 | 1 | 2 | 11 |
| **Total** | **23** | **3** | **6** | **4** | **32** |

---

## 4. Findings-Übersicht

_Policy: `fail-or-partial`_

| ID | Category | Severity | Status |
|---|---|---|---|
| ARCH-005 | ARCH | critical | partial |
| OBS-001 | OBS | high | partial |
| OBS-002 | OBS | high | partial |
| SDK-001 | SDK | high | fail |
| SEC-005 | SEC | high | fail |
| SEC-013 | SEC | high | partial |
| CH-004 | CH | medium | partial |
| SDK-002 | SDK | medium | partial |
| SDK-003 | SDK | medium | fail |

**Gesamt:** 9 Findings

---

## 5. Detail-Findings

### ARCH-005

# Finding: ARCH-005 — Keine Hardcoded Secrets

| Feld | Wert |
|---|---|
| **Severity** | critical |
| **Status** | open |
| **Server** | `srgssr-mcp` |
| **Check-Reference** | `ARCH-005` |
| **Audit-Datum** | 2026-05-06 |
| **Auditor** | Claude (mcp-audit-skill v0.5.0) |

## Observed Behavior

Pydantic-Settings-Pattern korrekt aufgesetzt: kein Klartext-Secret im Quellcode, `.env`-File nicht im Repo. Aber drei Secret-Hygiene-Lücken:

1. `consumer_secret: str` in `src/srgssr_mcp/config.py:30` ist als `str` typisiert, nicht als `pydantic.SecretStr` → akzidentielles Logging des Settings-Objekts würde den Secret als Klartext enthalten.
2. `.gitignore` enthält **kein** `.env` / `.env.local` / `secrets/` / `credentials/` → Risiko, dass ein Entwickler ein lokales `.env`-File aus Versehen committet.
3. Kein `.env.example` mit Placeholder-Werten → Onboarding-Hürde, plus keine kanonische Quelle für die erwarteten Env-Var-Namen.
4. Keine `gitleaks`/`trufflehog`-Action in `.github/workflows/` → kein automatisches Secret-Scanning auf Push.

## Expected Behavior

Per Best-Practice-Katalog (`ARCH-005`):

```python
# config.py
from pydantic import SecretStr

class Settings(BaseSettings):
    consumer_key: SecretStr = Field(..., validation_alias="SRGSSR_CONSUMER_KEY")
    consumer_secret: SecretStr = Field(..., validation_alias="SRGSSR_CONSUMER_SECRET")
```

```gitignore
# .gitignore
.env
.env.local
.env.*.local
secrets/
credentials/
```

```yaml
# .github/workflows/secret-scan.yml
- uses: gitleaks/gitleaks-action@v2
```

## Evidence

- `src/srgssr_mcp/config.py:29-30`:
  ```python
  consumer_key: str = Field(default="", validation_alias="SRGSSR_CONSUMER_KEY")
  consumer_secret: str = Field(default="", validation_alias="SRGSSR_CONSUMER_SECRET")
  ```
- `cat .gitignore` zeigt: `.venv/`, `__pycache__/`, `*.pyc` etc. — **kein `.env`**
- `ls -la /home/user/srgssr-mcp/ | grep -E "\.env"` → kein `.env.example`
- `grep -rE "gitleaks|trufflehog" .github/workflows/` → keine Treffer
- `grep -rE "(api[_-]?key|password|secret|token).*=.*['\"][^'\"]{16,}['\"]" src/` → keine Klartext-Secrets (gut)

## Risk Description

- **Konkret:** Wenn ein Entwickler lokal Tests mit echtem `consumer_secret` laufen lässt und `git add .` macht, landet die `.env` im Repo. `gitleaks` würde das fangen — aber ist nicht aktiv.
- **In-Memory-Leak:** Jede `repr(settings)` / `dict(settings)` / `logger.info("loaded", settings=settings)`-Operation würde den Klartext-Secret in Logs schreiben. Mit `SecretStr` wäre das `**********`.
- **Public Repo:** Das Repo ist auf GitHub öffentlich (`malkreide/srgssr-mcp`) — accidentaler Push einer `.env` ist sofort öffentlich; selbst `git rm` reicht nicht (history rewrite nötig).

## Remediation

```diff
# pyproject.toml: bereits pydantic >= 2.0 — keine Dep-Änderung nötig

# src/srgssr_mcp/config.py
- from pydantic import Field
+ from pydantic import Field, SecretStr

  class Settings(BaseSettings):
-     consumer_key: str = Field(default="", validation_alias="SRGSSR_CONSUMER_KEY")
-     consumer_secret: str = Field(default="", validation_alias="SRGSSR_CONSUMER_SECRET")
+     consumer_key: SecretStr = Field(default=SecretStr(""), validation_alias="SRGSSR_CONSUMER_KEY")
+     consumer_secret: SecretStr = Field(default=SecretStr(""), validation_alias="SRGSSR_CONSUMER_SECRET")
```

In `_http.py`, wo das Secret konsumiert wird:

```diff
- credentials = base64.b64encode(f"{consumer_key}:{consumer_secret}".encode()).decode()
+ credentials = base64.b64encode(
+     f"{consumer_key.get_secret_value()}:{consumer_secret.get_secret_value()}".encode()
+ ).decode()
```

```diff
# .gitignore
+ .env
+ .env.local
+ .env.*.local
+ secrets/
+ credentials/
```

```bash
# Neu: .env.example
SRGSSR_CONSUMER_KEY=your-consumer-key-here
SRGSSR_CONSUMER_SECRET=your-consumer-secret-here
SRGSSR_LOG_LEVEL=info
SRGSSR_MCP_TRANSPORT=stdio
```

```yaml
# Neu: .github/workflows/secret-scan.yml
name: Secret Scan
on: [push, pull_request]
jobs:
  gitleaks:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - uses: gitleaks/gitleaks-action@v2
```

## Effort Estimate

**S** — < 1 Tag. Vier kleine Änderungen plus ein neues Workflow-File.

## Dependencies / Blockers

Keine.

## Verification After Fix

- Re-Audit ARCH-005
- `grep -rE 'SecretStr' src/srgssr_mcp/config.py` muss 2 Treffer haben
- `cat .gitignore | grep -E '^\.env'` muss min. 1 Treffer haben
- `ls .env.example` muss existieren
- `ls .github/workflows/secret-scan.yml` muss existieren
- gitleaks-Action muss bei Test-Push einen Klartext-Secret fangen


### CH-004

# Finding: CH-004 — OGD-CH Lizenz-Compliance: CC BY 4.0 Attribution

| Feld | Wert |
|---|---|
| **Severity** | medium |
| **Status** | open |
| **Server** | `srgssr-mcp` |
| **Check-Reference** | `CH-004` |
| **Audit-Datum** | 2026-05-06 |
| **Auditor** | Claude (mcp-audit-skill v0.5.0) |

## Observed Behavior

SRG SSR Public API ist keine klassische OGD-CC-BY-4.0-Quelle (sie ist Public-but-Restricted: nicht-kommerzielle Nutzung erlaubt, kommerzielle Nutzung benötigt schriftliche Genehmigung über `api@srgssr.ch`). Lizenz-Lage ist im README dokumentiert, aber:

- Tool-Antworten enthalten kein explizites `source` / `license` / `provenance`-Feld
- Im README fehlt eine "Datenquellen & Lizenzen"-Tabelle wie im OGD-Pass-Pattern verlangt

## Expected Behavior

Per Best-Practice-Katalog (`CH-004`): Auch bei Single-Provider-Servern soll Provenance maschinenlesbar exponiert werden, damit nachgeschaltete LLMs/Agenten die Datenherkunft nachvollziehen können.

```python
class VotationsResponse(BaseModel):
    source: str = "SRG SSR Public API V2"
    license: str = "SRG SSR Terms of Use (non-commercial)"
    provenance_url: str = "https://developer.srgssr.ch"
    results: list[Votation]
    count: int
```

Plus README-Tabelle:

```markdown
## Datenquellen & Lizenzen

| Cluster | Quelle | Lizenz | Kommerziell |
|---|---|---|---|
| Weather | SRF Meteo (api.srgssr.ch) | SRG SSR Terms of Use | nur mit Genehmigung |
| Polis | SRG SSR Polis | SRG SSR Terms of Use | nur mit Genehmigung |
| ... | ... | ... | ... |
```

## Evidence

- `grep -rnE '"source"|"license"|"provenance"|"attribution"' src/` → keine Treffer
- `grep -inE 'cc by|opendata|ogd' README.md README.de.md` → keine OGD-Erwähnung
- `README.md:54`: "Terms of use: SRG SSR APIs are available for non-commercial use. For commercial use, contact api@srgssr.ch"
- `README.de.md:344`: gleiche Information auf Deutsch
- `BASE_URL = "https://api.srgssr.ch"` (`_http.py:17`) — Single-Provider, Provenance implizit

## Risk Description

- **Compliance:** Bei kommerzieller Nutzung durch Endkunden ist die Lizenz-Bedingung über die LLM-Antwort nicht ersichtlich. Risiko, dass User SRG-SSR-Daten in kommerziellem Kontext nutzen ohne sich der Restriktion bewusst zu sein.
- **Geringer als bei klassischem OGD:** Single-Provider, Lizenz im README dokumentiert, MIT-Lizenz für den Code selbst.

## Remediation

Phase 1 (S): README-Erweiterung um eine "Datenquellen & Lizenzen"-Sektion (DE und EN) mit Tabelle pro Cluster.

Phase 2 (M, optional, hängt mit SDK-002 zusammen): Strukturierter Output-Envelope mit `source` / `license` / `provenance_url`-Feldern. Sinnvoll, wenn SDK-002 sowieso angegangen wird.

```diff
+ # Neu in README.md:
+ ## Data Sources & Licenses
+
+ All data is fetched live from SRG SSR Public API V2 (https://developer.srgssr.ch).
+ Use is governed by the SRG SSR Terms of Use:
+
+ - Non-commercial use: free, no application required.
+ - Commercial use: written permission required via api@srgssr.ch.
+
+ | Cluster | Provider | License | Notes |
+ |---|---|---|---|
+ | Weather | SRF Meteo | SRG SSR Terms | Geo-restricted to Switzerland |
+ | Video / Audio / EPG | SRF / RTS / RSI / RTR / SWI | SRG SSR Terms | Metadata only, not stream content |
+ | Polis | SRG SSR Polis | SRG SSR Terms | Historical data since 1900 |
```

## Effort Estimate

**S** — Phase 1 < 1 Tag. Phase 2 zusammen mit SDK-002 (Output-Envelope).

## Dependencies / Blockers

Phase 2 hängt von SDK-002 ab.

## Verification After Fix

- Re-Audit CH-004
- `grep -inE 'data sources|datenquellen' README.md README.de.md` muss min. 1 Treffer liefern
- (Phase 2) `grep -rE '"source"|"license"' src/` muss in Output-Models Treffer haben


### OBS-001

# Finding: OBS-001 — Protocol vs. Execution Errors: korrekte Trennung

| Feld | Wert |
|---|---|
| **Severity** | high |
| **Status** | open |
| **Server** | `srgssr-mcp` |
| **Check-Reference** | `OBS-001` |
| **Audit-Datum** | 2026-05-06 |
| **Auditor** | Claude (mcp-audit-skill v0.5.0) |

## Observed Behavior

Alle 15 Tools fangen Exceptions mit `try/except` und delegieren an `_handle_error()`, das einen deutschsprachigen Error-String zurückgibt. Das vermeidet JSON-RPC-Crashes bei API-/Validierungs-Fehlern (Pass-Pattern für Execution-Errors).

Aber:

- Keine standardisierten JSON-RPC-Codes (-326xx / -320xx) als Konstanten
- Kein expliziter `{"isError": true, "content": [TextContent(...)]}`-Envelope — Errors werden als plain `str` retourniert
- Pydantic-ValidationErrors / Tool-Lookup-Fehler werden vom FastMCP-Framework korrekt als Protocol-Errors gehandhabt (FastMCP-Default), aber nicht explizit im Code dokumentiert

## Expected Behavior

Per Best-Practice-Katalog (`OBS-001`): Klare Trennung von Protocol-Errors (FastMCP-Default ist OK) und Execution-Errors mit standardisiertem Envelope:

```python
from mcp.types import TextContent

async def srgssr_polis_get_votations(params: PolisListInput) -> list[TextContent] | str:
    try:
        ...
        return formatted_markdown
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            return [TextContent(type="text", text="Rate-Limit überschritten...")]
            # FastMCP setzt isError automatisch bei TextContent-Liste mit Fehler-Markierung
```

## Evidence

- `src/srgssr_mcp/_http.py:_handle_error`:
  - 401 → "Fehler 401: Ungültige API-Credentials..."
  - 403 / 404 / 429 / Timeout: ähnliche Pattern (sanitisierte DE-Strings)
  - **Default-Fallback:** `f"Unerwarteter Fehler ({type(e).__name__}): {e}"` — kann Internals leaken
- `grep -rE "INVALID_TOOL|INVALID_PARAMS|EXECUTION_FAILED|-326|-320" src/` → keine Treffer
- `grep -rE "isError|TextContent" src/` → keine Treffer

## Risk Description

- **Geringer im Read-Only-Scope:** Keine Write-Pfade, keine destruktiven Operationen — Error-Klarheit hat begrenzten Sicherheitsimpact.
- **LLM-UX:** Plain-String-Returns bei Fehlern werden vom LLM nicht zuverlässig als Error erkannt → das LLM könnte den deutschen Fehlertext als gültige Antwort durchreichen ("Der Wetterdienst sagte, dass die API-Credentials ungültig sind"). Mit `isError: true`-Envelope kann der Client das gezielter behandeln.
- **Default-Fallback-Leak:** `str(e)` kann bei `socket.gaierror` interne IPs / Hostnames enthalten — kleine Information-Disclosure-Lücke.

## Remediation

Phase 1 (S, hauptsächlich Default-Fallback härten):

```diff
# _http.py, _handle_error
- return f"Unerwarteter Fehler ({type(e).__name__}): {e}"
+ # Internals nicht durchreichen — nur Exception-Typ
+ logger.error("unhandled_exception", exc_info=e)
+ return f"Unerwarteter Fehler. Details siehe Server-Log (Typ: {type(e).__name__})."
```

Phase 2 (M, isError-Envelope):

```diff
- return error_text  # plain str
+ from mcp.types import TextContent
+ return [TextContent(type="text", text=error_text)]
+ # FastMCP behandelt list[TextContent] mit Fehler-Inhalt korrekt
```

Phase 3 (S, JSON-RPC-Code-Konstanten als Doku):

```python
# Neu: src/srgssr_mcp/errors.py
JSONRPC_INVALID_PARAMS = -32602
EXECUTION_RATE_LIMIT = -32001  # FastMCP-spezifisch
EXECUTION_UPSTREAM_ERROR = -32004
# Verwendet als Doku-Constants in raise / Logging
```

## Effort Estimate

**S/M** — Phase 1 < 1 Tag. Phase 2 + 3 zusammen 1–2 Tage.

## Dependencies / Blockers

Keine.

## Verification After Fix

- Re-Audit OBS-001
- Default-Fallback enthält kein `{e}` mehr (nur Typ)
- Optional Phase 2: `grep -rE 'TextContent|isError' src/` zeigt strukturierte Error-Returns


### OBS-002

# Finding: OBS-002 — Mask Error Details: keine Stacktraces / SQL ans LLM

| Feld | Wert |
|---|---|
| **Severity** | high |
| **Status** | open |
| **Server** | `srgssr-mcp` |
| **Check-Reference** | `OBS-002` |
| **Audit-Datum** | 2026-05-06 |
| **Auditor** | Claude (mcp-audit-skill v0.5.0) |

## Observed Behavior

Gut: keine `traceback.format_exc()` / `sys.exc_info()`-Outputs in Tool-Returns. `_handle_error()` liefert sanitisierte deutsche Error-Strings für 401/403/404/429/Timeout. structlog-Logger nutzt JSONRenderer mit `format_exc_info`-Processor → Stacktraces landen im Log (gewollt), nicht im Tool-Result.

Lücken:

1. `mask_error_details=True` (FastMCP-Option) ist NICHT gesetzt im Konstruktor — bei unhandled Exceptions im Framework greift der FastMCP-Default (kann je nach Version mehr durchreichen als gewünscht)
2. Default-Fallback in `_handle_error` gibt `str(e)` durch: `f"Unerwarteter Fehler ({type(e).__name__}): {e}"` — kann interne Details enthalten (siehe OBS-001)

## Expected Behavior

Per Best-Practice-Katalog (`OBS-002`): Defense-in-Depth mit zwei Schutzlagen:

```python
mcp = FastMCP("srgssr_mcp", mask_error_details=True, ...)
```

Plus Code-Layer:

```python
def _handle_error(e: Exception) -> str:
    if isinstance(e, ...):
        return "..."  # known error → sanitized message
    # Unknown: log full, return generic
    logger.error("unhandled_exception", exc_info=e)
    return "Interner Serverfehler. Bitte später erneut versuchen."
```

## Evidence

- `grep -rE 'mask_error_details' src/` → keine Treffer
- `src/srgssr_mcp/_app.py`: `mcp = FastMCP("srgssr_mcp", instructions=...)` — kein `mask_error_details=True`
- `grep -rE 'traceback|format_exc|sys\.exc_info' src/` → keine Treffer (gut)
- `_handle_error`-Default: `f"Unerwarteter Fehler ({type(e).__name__}): {e}"` — leakt potentiell

## Risk Description

- **Information Disclosure:** Bei `socket.gaierror` (z.B. DNS-Probleme im VPC) enthält `str(e)` Hostname/IP-Internals.
- **Bei `pydantic.ValidationError` (Tool-Inputs):** FastMCP-Default zeigt vollen Schema-Pfad — bei sehr langem Pfad informativ für Angreifer.
- **Real-Risiko klein bei Read-Only / Public Data:** Server hat keinen DB-Layer mit SQL-Strings, keine Secrets im Schema. Trotzdem Defense-in-Depth wert.

## Remediation

```diff
# src/srgssr_mcp/_app.py
- mcp = FastMCP("srgssr_mcp", instructions=...)
+ mcp = FastMCP("srgssr_mcp", instructions=..., mask_error_details=True)
```

```diff
# src/srgssr_mcp/_http.py — _handle_error Default-Fallback
- return f"Unerwarteter Fehler ({type(e).__name__}): {e}"
+ logger.error("unhandled_exception", exc_info=e)
+ return f"Unerwarteter Fehler. Details siehe Server-Log (Typ: {type(e).__name__})."
```

Plus Test:

```python
# tests/test_unit.py
def test_handle_error_no_internals_leak():
    err = socket.gaierror("getaddrinfo: nodename nor servname provided, or not known")
    msg = _handle_error(err)
    assert "getaddrinfo" not in msg  # no internal-detail leak
    assert "nodename" not in msg
```

## Effort Estimate

**S** — < 1 Tag. Zwei kleine Änderungen plus ein Test.

## Dependencies / Blockers

Synergetisch mit OBS-001 (gleicher Hot-Path im Code), aber unabhängig.

## Verification After Fix

- Re-Audit OBS-002
- `grep -rE 'mask_error_details=True' src/` muss 1 Treffer in `_app.py` haben
- Default-Fallback enthält kein `{e}` mehr
- Test `test_handle_error_no_internals_leak` muss grün sein


### SDK-001

# Finding: SDK-001 — FastMCP Lifespan via @asynccontextmanager + AsyncExitStack

| Feld | Wert |
|---|---|
| **Severity** | high |
| **Status** | open |
| **Server** | `srgssr-mcp` |
| **Check-Reference** | `SDK-001` |
| **Audit-Datum** | 2026-05-06 |
| **Auditor** | Claude (mcp-audit-skill v0.5.0) |

## Observed Behavior

Kein `@asynccontextmanager`-Lifespan im Repository definiert. Der FastMCP-Konstruktor in `src/srgssr_mcp/_app.py` wird ohne `lifespan=`-Argument aufgerufen:

```python
mcp = FastMCP("srgssr_mcp", instructions=...)  # kein lifespan=
```

httpx-Clients werden pro API-Call neu instanziiert in `src/srgssr_mcp/_http.py:122` und `:151`:

```python
async with httpx.AsyncClient(timeout=TIMEOUT) as client:
    ...  # neuer Client pro Tool-Aufruf, kein Connection-Pooling
```

## Expected Behavior

FastMCP-Best-Practice (siehe Check `SDK-001`): Ein einziger `httpx.AsyncClient` wird in einer Lifespan-Funktion erstellt und pro Server-Instanz wiederverwendet:

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastMCP):
    async with httpx.AsyncClient(timeout=TIMEOUT) as http:
        app.state.http = http
        yield
        # Cleanup automatisch via __aexit__

mcp = FastMCP("srgssr_mcp", lifespan=lifespan, ...)
```

Tools beziehen den Client via `ctx.fastmcp.state.http` statt jedes Mal neu zu erzeugen.

## Evidence

- `src/srgssr_mcp/_app.py`: FastMCP-Konstruktor ohne `lifespan=`
- `src/srgssr_mcp/_http.py:122`: `async with httpx.AsyncClient(timeout=TIMEOUT) as client:` in `_get_access_token`
- `src/srgssr_mcp/_http.py:151`: gleiches Pattern in `_api_get`
- `grep -rE '@asynccontextmanager' src/` → keine Treffer
- `grep -rE 'AsyncExitStack' src/` → keine Treffer

## Risk Description

- **Performance:** Pro Tool-Call ein neuer TCP-Handshake + TLS-Setup zu `api.srgssr.ch`. Bei `srgssr_daily_briefing` (mehrere parallele Sub-Calls via `asyncio.gather`) summiert sich das. Connection-Pooling wäre ein Faktor 2–4× schneller bei mehreren Tools in Folge.
- **Resource-Leak-Risiko:** Bei einer Exception im Tool-Body kann der Client unsauber stehen bleiben (mitigiert durch `async with`, aber jede neue Instanz ist ein neuer Failure-Punkt).
- **Token-Cache-Race:** Der `_token_cache`-Dict in `_http.py` ist ein Modul-Level-Mutable — bei mehreren konkurrenten Tool-Calls ohne Lock gibt es einen kleinen Race zwischen Cache-Hit und Refresh. Bei pro-Call-Client würde das nur durch Glück nicht auffallen.

## Remediation

```diff
# src/srgssr_mcp/_app.py
+ from contextlib import asynccontextmanager
+ import httpx
+
+ @asynccontextmanager
+ async def lifespan(app):
+     async with httpx.AsyncClient(timeout=TIMEOUT) as http:
+         app.state.http = http
+         yield
+
- mcp = FastMCP("srgssr_mcp", instructions=...)
+ mcp = FastMCP("srgssr_mcp", lifespan=lifespan, instructions=...)
```

```diff
# src/srgssr_mcp/_http.py — _api_get / _get_access_token
- async with httpx.AsyncClient(timeout=TIMEOUT) as client:
-     response = await client.get(...)
+ http = ctx.fastmcp.state.http  # ctx als zusätzlicher Param injiziert
+ response = await http.get(...)
```

Schritte:
1. Lifespan in `_app.py` definieren
2. `_api_get`/`_get_access_token` so refactorn, dass sie den shared `http`-Client via `ctx` erhalten
3. Tools erweitern um `ctx: Context`-Parameter (siehe SDK-003)
4. Token-Cache mit `asyncio.Lock` schützen

## Effort Estimate

**M** — 1–3 Tage. 15 Tools müssen `ctx`-Parameter aufnehmen und `_api_get`-Aufrufe entsprechend angepasst werden; Tests (`tests/test_unit.py`) brauchen httpx-Mock-Anpassung.

## Dependencies / Blockers

Hängt zusammen mit SDK-003 (`ctx`-Injection in Tools) — sinnvoll als ein gemeinsamer Refactor.

## Verification After Fix

- Re-Audit von SDK-001
- `grep -rE '@asynccontextmanager' src/` muss min. 1 Treffer liefern
- `grep -rE 'FastMCP\([^)]*lifespan=' src/` muss 1 Treffer in `_app.py` liefern
- `grep -rnE 'httpx\.AsyncClient' src/` darf nur noch in der Lifespan-Funktion vorkommen


### SDK-002

# Finding: SDK-002 — Pydantic v2 / TypedDict / Dataclass als Tool-Returns

| Feld | Wert |
|---|---|
| **Severity** | medium |
| **Status** | open |
| **Server** | `srgssr-mcp` |
| **Check-Reference** | `SDK-002` |
| **Audit-Datum** | 2026-05-06 |
| **Auditor** | Claude (mcp-audit-skill v0.5.0) |

## Observed Behavior

Pydantic >= 2.0 in `pyproject.toml` (PASS). Tool-**Inputs** sind alle als `BaseModel`-Subklassen typisiert (10 Models: `EpgProgramsInput`, `AudioEpisodesInput`, `PolisListInput`/`ResultInput`, `VideoShows`/`Episodes`/`Livestreams`, `WeatherSearch`/`Forecast`, `DailyBriefingInput`).

Aber: Tool-**Outputs** sind durchgehend `-> str` (Markdown-formatierte Strings) — kein strukturierter Output-Envelope mit `source` / `provenance` / `results` / `count`.

`ResponseFormat`-StrEnum (markdown/json) existiert in `_app.py`, wird aber nicht von Tool-Returns konsumiert.

## Expected Behavior

Per Best-Practice-Katalog (`SDK-002`): Strukturierte Output-Models, damit FastMCP das Output-Schema im `tools/list`-Manifest exponieren kann und Folge-Tool-Calls präzise geplant werden:

```python
class VotationsResponse(BaseModel):
    source: Literal["SRG SSR Public API V2"]
    provenance: Literal["live_api", "cached"]
    fetched_at: datetime
    results: list[Votation]
    count: int

@mcp.tool(...)
async def srgssr_polis_get_votations(params: PolisListInput) -> VotationsResponse:
    ...
```

## Evidence

- `grep -rnE 'async def srgssr_' src/` → 15/15 Tools haben `-> str` als Return-Annotation
- `grep -rE "BaseModel|ConfigDict" src/srgssr_mcp/tools/` → 10 Input-BaseModel-Klassen
- `grep -rE "source|provenance|envelope" src/srgssr_mcp/tools/` → keine Treffer
- `_app.py`: `class ResponseFormat(StrEnum): MARKDOWN, JSON` — definiert, aber ungenutzt in Tool-Returns

## Risk Description

- **Kein Sicherheits-Risiko, eher LLM-UX:** Markdown-Strings sind für LLMs gut lesbar, aber für maschinen-lesbare Folgeschritte ungeeignet (z.B. ein Agent, der `count` aus der Response in einer Schleife verwendet, müsste den Markdown parsen).
- **Output-Schema im Tool-Manifest fehlt:** FastMCP kann ohne typisierte Returns kein Output-Schema exponieren → LLM rät aus dem Markdown-Format.
- **Provenance/Source nicht maschinenlesbar:** Hängt zusammen mit CH-004 (Lizenz-Attribution).

## Remediation

Phase 1 (M, alle 15 Tools): Output-Models einführen pro Cluster.

```diff
+ # src/srgssr_mcp/_models.py (neu)
+ class ResponseEnvelope(BaseModel):
+     source: str = "SRG SSR Public API V2"
+     provenance: Literal["live_api"] = "live_api"
+     fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
+
+ class VotationsResponse(ResponseEnvelope):
+     results: list[Votation]
+     count: int
+
+ # ... pro Cluster ein Response-Model

# tools/polis.py
- async def srgssr_polis_get_votations(params: PolisListInput) -> str:
-     ...
-     return _format_votations(data)
+ async def srgssr_polis_get_votations(params: PolisListInput) -> VotationsResponse:
+     ...
+     return VotationsResponse(results=data, count=len(data))
```

FastMCP serialisiert `BaseModel`-Returns automatisch als JSON. Falls Markdown-UX gewünscht bleibt: `ResponseFormat`-Enum konsumieren.

Phase 2 (S, optional): Markdown-Generator als separater Tool-Export für Backwards-Compat.

## Effort Estimate

**M** — 1–3 Tage. 15 Tools × ~15 min Refactoring + Test-Anpassungen + Snapshot-Tests für die neuen Schemas.

## Dependencies / Blockers

Sinnvoll gemeinsam mit CH-004 (Provenance-Felder im Envelope) zu lösen.

## Verification After Fix

- Re-Audit SDK-002
- `grep -rE '-> [A-Z][a-zA-Z]+Response' src/srgssr_mcp/tools/` muss min. 15 Treffer haben
- FastMCP `tools/list` muss `outputSchema` für jedes Tool ausgeben


### SDK-003

# Finding: SDK-003 — Context Injection für Progress Reports und Logging

| Feld | Wert |
|---|---|
| **Severity** | medium |
| **Status** | open |
| **Server** | `srgssr-mcp` |
| **Check-Reference** | `SDK-003` |
| **Audit-Datum** | 2026-05-06 |
| **Auditor** | Claude (mcp-audit-skill v0.5.0) |

## Observed Behavior

Kein einziges der 15 Tools nutzt den FastMCP-`Context`-Parameter:

```bash
$ grep -rB1 -A5 "@mcp\.tool" src/ | grep -E "ctx:\s*Context|Context\)"
# (keine Treffer)
$ grep -rnE 'ctx\.(info|warning|error|debug|report_progress|elicit|sample)' src/
# (keine Treffer)
```

Tool-Funktionen sind aktuell typisiert als `async def srgssr_<name>(params: <X>Input) -> str`. Damit fehlen alle Context-basierten Capabilities: Progress-Reports, Per-Call-Logging, Client-Info, Sampling, Elicitation.

## Expected Behavior

Per Best-Practice-Katalog (`SDK-003`): Tools deklarieren `ctx: Context` als optionalen Parameter und nutzen mindestens:

- `await ctx.info("tool_invoked", ...)` am Start
- `await ctx.report_progress(current, total)` bei längeren Operationen (`srgssr_daily_briefing`, EPG-Iterationen)
- `await ctx.error(...)` bei Fehlerpfaden statt nur Return-String

```python
@mcp.tool(...)
async def srgssr_polis_get_votations(
    params: PolisListInput,
    ctx: Context | None = None,
) -> str:
    if ctx:
        await ctx.info("polis_search_started", year=params.year)
    ...
```

## Evidence

- `src/srgssr_mcp/tools/aggregation.py:135`: `await asyncio.gather(weather_result, epg_result)` — keine `ctx.report_progress` zwischen den parallelen Sub-Calls
- `src/srgssr_mcp/tools/polis.py:168, 265, 367`: For-Loops über Listen ohne Progress-Hinweis
- `grep -rE "logger\." src/srgssr_mcp/tools/` → keine `logger.`-Aufrufe in Tools (nur shared structlog auf HTTP-Layer)

## Risk Description

- **UX:** Bei `srgssr_daily_briefing` mit upstream-Latency >2 s sieht der Claude-Client keine Aktivität — wirkt wie Hänger.
- **Observability:** Tool-Invocations werden nicht per-Call geloggt. Fehlersuche im Produktionsfall ist auf den shared HTTP-Logger angewiesen, der Tool-Identität nicht binden kann (siehe OBS-003).
- **Future-Proofing:** Sampling und Elicitation (HITL-Pattern) sind ohne Context-Parameter nicht erreichbar — das blockiert Erweiterungen wie LLM-gestützte Datenklassifikation oder Confirmations bei Write-Tools.

## Remediation

Pro Tool-Datei (audio.py, video.py, weather.py, epg.py, polis.py, aggregation.py):

```diff
- @mcp.tool(name="srgssr_weather_current", ...)
- async def srgssr_weather_current(params: WeatherCurrentInput) -> str:
+ @mcp.tool(name="srgssr_weather_current", ...)
+ async def srgssr_weather_current(
+     params: WeatherCurrentInput,
+     ctx: Context | None = None,
+ ) -> str:
+     if ctx:
+         await ctx.info("weather_current_invoked", lat=params.lat, lon=params.lon)
      ...
```

Zusätzlich für `srgssr_daily_briefing`:

```diff
+ if ctx:
+     await ctx.report_progress(0, 2, message="Wetter-Daten holen")
  weather_result = await srgssr_weather_get_current(...)
+ if ctx:
+     await ctx.report_progress(1, 2, message="EPG-Daten holen")
  epg_result = await srgssr_epg_get_programs(...)
```

## Effort Estimate

**S** — < 1 Tag. Pro Tool ~10 min Refactoring × 15 Tools = ~2.5 h plus Tests-Anpassung.

## Dependencies / Blockers

Sinnvoll gemeinsam mit SDK-001 (Lifespan) zu lösen, weil Tools dann auch den shared httpx-Client via `ctx.fastmcp.state.http` beziehen.

## Verification After Fix

- Re-Audit SDK-003
- `grep -rE 'ctx:\s*Context' src/srgssr_mcp/tools/` muss min. 15 Treffer liefern
- `grep -rE 'await ctx\.(info|warning|error|report_progress)' src/` muss min. 15 Treffer liefern


### SEC-005

# Finding: SEC-005 — DNS-Rebinding-Prevention: DNS-Pinning gegen TOCTOU

| Feld | Wert |
|---|---|
| **Severity** | high |
| **Status** | open |
| **Server** | `srgssr-mcp` |
| **Check-Reference** | `SEC-005` |
| **Audit-Datum** | 2026-05-06 |
| **Auditor** | Claude (mcp-audit-skill v0.5.0) |

## Observed Behavior

`_validate_url_safe()` in `src/srgssr_mcp/_http.py` macht eine DNS-Resolution für die IP-Allowlist-Prüfung, gibt dann aber die Original-URL (mit Hostname) an httpx weiter. httpx löst den Hostname intern ein zweites Mal auf — klassisches TOCTOU-Fenster für DNS-Rebinding.

```python
# Vereinfacht aus _http.py:
def _validate_url_safe(url: str) -> None:
    ...
    addr_infos = socket.getaddrinfo(hostname, None)  # 1. Resolution für Range-Check
    for info in addr_infos:
        if _is_private_ip(info[4][0]):
            raise ValueError("blocked")

# Aufruf:
_validate_url_safe(TOKEN_URL)
async with httpx.AsyncClient(...) as client:
    response = await client.get(TOKEN_URL)  # 2. Resolution, möglicherweise andere IP
```

Kein DNS-Pinning, kein Custom-Transport mit gepinnter IP, keine `Host`-Header-Manipulation für SNI.

## Expected Behavior

Per Best-Practice-Katalog (`SEC-005`): Nur **eine** DNS-Resolution; der gefundene IP wird als Connect-Target genutzt, der Hostname nur für SNI/Host-Header:

```python
import httpx, socket

class PinnedTransport(httpx.AsyncHTTPTransport):
    def __init__(self, hostname: str, **kwargs):
        addr = socket.getaddrinfo(hostname, None)[0][4][0]
        # ... Validation der IP
        self._pinned_url = lambda url: url.copy_with(host=addr)
        super().__init__(**kwargs)

# Oder: Egress-Proxy (Stripe Smokescreen) via HTTPS_PROXY-Env-Var.
```

## Evidence

- `src/srgssr_mcp/_http.py`: `socket.getaddrinfo(hostname, None)` — nur einmal, dann Original-URL an httpx
- `grep -rE 'replace\(.*hostname.*resolved|Host:.*hostname|pinned_url' src/` → keine Treffer
- `grep -rE 'sni_hostname|SSLContext' src/` → keine Treffer
- `ALLOWED_HOSTS = frozenset({"api.srgssr.ch"})` (`_http.py:34`) — Mitigant: nur 1 Domain im Scope

## Risk Description

- **Theoretisches Worst-Case:** Angreifer kontrolliert DNS für `api.srgssr.ch` → Validation sieht öffentliche IP, httpx bekommt private/loopback-IP → SSRF in interne Netze.
- **Realistisches Risiko:** Niedrig, weil:
  - SRG SSR kontrolliert die Domain
  - Single-Host-Allowlist (kein User-supplied URL)
  - Read-only-Server, keine Write-Pfade
- **Defense-in-Depth-Lücke:** Der Check verlangt explizit DNS-Pinning oder Egress-Proxy als Layer-2 — bei Cloud-Deployment mit erweitertem Scope (mehrere Domains, weniger Trust) wird das Pflicht.

## Remediation

**Option A (Code-Layer-Fix):**

```diff
+ class PinnedTransport(httpx.AsyncHTTPTransport):
+     async def handle_async_request(self, request):
+         resolved_ip = socket.getaddrinfo(request.url.host, None)[0][4][0]
+         _validate_ip_allowed(resolved_ip)
+         # Replace host in URL with IP, keep Host header for SNI
+         new_url = request.url.copy_with(host=resolved_ip)
+         new_request = request.copy_with(url=new_url, headers={**request.headers, "Host": request.url.host})
+         return await super().handle_async_request(new_request)
+
+ transport = PinnedTransport()
- async with httpx.AsyncClient(timeout=TIMEOUT) as client:
+ async with httpx.AsyncClient(timeout=TIMEOUT, transport=transport) as client:
```

**Option B (Network-Layer-Fix):** Egress-Proxy einsetzen — z.B. `stripe/smokescreen` mit Allowlist `api.srgssr.ch`. Setzt `HTTPS_PROXY=http://smokescreen:4750` als Env-Var. Smokescreen macht DNS-Pinning automatisch.

Option B ist robuster (sprachunabhängig, zentralisierbar, auditierbar) und wird in `docs/network-egress.md` bereits als Defense-in-Depth-Plan erwähnt.

## Effort Estimate

**M** — 1–3 Tage für Option A inkl. Tests gegen Mock-Resolver. Option B ist deployment-spezifisch (Container-Sidecar).

## Dependencies / Blockers

Keine. Kann unabhängig von SDK-001 / SEC-021 implementiert werden.

## Verification After Fix

- Re-Audit SEC-005
- Test mit Mock-Resolver, der zwei verschiedene IPs returnt — der zweite Lookup darf das Ergebnis nicht ändern
- `grep -rE 'PinnedTransport|sni_hostname' src/` muss min. 1 Treffer liefern (Option A) oder Doc-Update zum Egress-Proxy (Option B)


### SEC-013

# Finding: SEC-013 — API-Key-Storage: Secret Manager statt Plain-Text Env-Vars

| Feld | Wert |
|---|---|
| **Severity** | high |
| **Status** | open |
| **Server** | `srgssr-mcp` |
| **Check-Reference** | `SEC-013` |
| **Audit-Datum** | 2026-05-06 |
| **Auditor** | Claude (mcp-audit-skill v0.5.0) |

## Observed Behavior

Secret-Storage-Reife: **Stufe 1** (Plain Env-Var via `pydantic-settings.BaseSettings`). `SRGSSR_CONSUMER_KEY` / `SRGSSR_CONSUMER_SECRET` werden aus Environment oder `.env`-File geladen (`src/srgssr_mcp/config.py:29-30`).

Profil sagt `data_class=Public Open Data` → laut Check ist Stufe 1 dafür akzeptabel — **wenn dokumentiert**.

Lücken:

1. Keine `docs/secret-management.md` mit Stufe-1-Akzeptanz-Begründung
2. `lru_cache(maxsize=1)` auf `get_settings()` → Secret-Rotation erfordert Process-Restart, kein TTL-Cache
3. Bei zukünftigem K8s-Deployment (siehe `docs/network-egress.md`) ist Stufe 3 (Secret Manager) zu erwägen — aktuell keine `boto3` / `azure-keyvault` / `google-cloud-secret-manager`-Dep
4. Synergetisch mit ARCH-005: `consumer_secret: str` (nicht `SecretStr`) → In-Memory-Klartext

## Expected Behavior

Per Best-Practice-Katalog (`SEC-013`): Stufen-Eskalation mit dokumentierter Begründung.

```markdown
# docs/secret-management.md

## Aktuelle Stufe: 1 (Plain Env-Var)

Begründung: `data_class=Public Open Data`, kein PII-Bezug, keine destruktiven
Operationen (`write_capable=false`). Stufe 1 ist gemäss SEC-013-Pass-Pattern
akzeptabel.

## Eskalations-Trigger

Bei einem der folgenden Trigger ist auf Stufe 3 (Secret Manager) zu wechseln:
- Cloud-Deployment (K8s, ECS, Render)
- Multi-Tenant-Betrieb
- Tool-Set erweitert um Write-Pfade
```

Plus TTL-Cache:

```python
from cachetools import TTLCache, cached

@cached(cache=TTLCache(maxsize=1, ttl=300))
def get_settings() -> Settings:
    return Settings()
```

## Evidence

- `src/srgssr_mcp/config.py:51`: `@lru_cache(maxsize=1)` → keine Rotation ohne Restart
- `grep -rE 'boto3|secretsmanager|hvac|azure-keyvault|google-cloud-secret-manager' pyproject.toml` → keine Treffer
- `ls docs/` → nur `network-egress.md`, keine `secret-management.md`

## Risk Description

- **Aktuell akzeptabel:** Public Open Data, Stufe 1 ist im Check explizit erlaubt.
- **Operationelles Risiko (Rotation):** Falls SRG SSR die Credentials rotieren würde (oder sie ein Leak hätten), müsste der Server-Prozess neu gestartet werden, weil `lru_cache` für die Lifetime persistiert. Bei Cloud-Deployment mit langlebigen Pods ist das ein Problem.
- **Skalierungsrisiko:** Bei zukünftigem K8s-Rollout (siehe `docs/network-egress.md`) ist Stufe 1 nicht mehr ausreichend — External Secrets Operator + AWS Secrets Manager (eu-central-1 oder Azure Key Vault Switzerland North) wäre der Standard.

## Remediation

Phase 1 (S, sofort): Doku-Stub erstellen.

```diff
+ # docs/secret-management.md (neu)
+
+ # Secret Management
+
+ ## Aktuelle Stufe
+
+ Stufe 1 (Plain Env-Var via pydantic-settings).
+
+ ## Akzeptanz-Begründung
+
+ - `data_class=Public Open Data` (SRG SSR Public API)
+ - `write_capable=false`
+ - Single-Tenant (kein Multi-User-Server)
+
+ ## Eskalation auf Stufe 3 (Secret Manager) bei:
+ - Cloud-Deployment (K8s/ECS/Render)
+ - Multi-Tenant-Betrieb
+ - Tool-Set erweitert um Write-Pfade
```

Phase 2 (S): TTL-Cache mit Refresh ohne Restart.

```diff
# pyproject.toml
+ "cachetools>=5.0.0",

# src/srgssr_mcp/config.py
- from functools import lru_cache
+ from cachetools import TTLCache, cached
- @lru_cache(maxsize=1)
+ @cached(cache=TTLCache(maxsize=1, ttl=300))  # Re-read every 5 min
  def get_settings() -> Settings:
      return Settings()
```

Phase 3 (M, bei Cloud-Migration): External Secrets Operator + AWS/Azure Secret Manager. Plan in `docs/secret-management.md` skizzieren.

## Effort Estimate

**S** für Phase 1 + 2. **M** für Phase 3 (deployment-spezifisch).

## Dependencies / Blockers

Synergetisch mit ARCH-005 (Secret-Hygiene) — gleiche Files betroffen.

## Verification After Fix

- Re-Audit SEC-013
- `ls docs/secret-management.md` muss existieren
- `grep -rE 'TTLCache|cachetools' src/srgssr_mcp/config.py` muss min. 1 Treffer haben
- (Phase 3) Wenn cloud-deployed: External Secrets Manager dokumentiert


---

## 6. Remediation-Plan

### Empfohlene Reihenfolge

1. **ARCH-005** (critical, partial)
2. **OBS-001** (high, partial)
3. **OBS-002** (high, partial)
4. **SDK-001** (high, fail)
5. **SEC-005** (high, fail)
6. **SEC-013** (high, partial)
7. **CH-004** (medium, partial)
8. **SDK-002** (medium, partial)
9. **SDK-003** (medium, fail)

---

## 7. Audit-Metadata

| Feld | Wert |
|---|---|
| skill_version | `0.9.x` |
| catalog_version | `v0.5.0 (68 checks)` |
| audit_date | `2026-05-06` |


_Generated by tools/build_report.py — do not edit by hand._
