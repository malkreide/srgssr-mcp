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
