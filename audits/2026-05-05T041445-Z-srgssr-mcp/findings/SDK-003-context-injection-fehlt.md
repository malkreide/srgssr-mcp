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
