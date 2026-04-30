# Finding: ARCH-007 — Capability-Aggregation: Composability intern, Atomarität extern

| Feld | Wert |
|---|---|
| **Severity** | medium |
| **Status** | fixed |
| **Server** | `srgssr-mcp` |
| **Check-Reference** | `ARCH-007` |
| **PDF-Reference** | Sec 2.3 |
| **Audit-Datum** | 2026-04-30 |
| **Auditor** | Claude (mcp-audit-skill v0.5.0) |

## Observed Behavior

Vor dem Fix waren alle 13 Tools **Thin Wrappers** um genau einen SRG SSR
API-Endpoint:

- Kein `asyncio.gather` im Server-Code
- Jedes Tool = ein Roundtrip
- Cross-Domain-Queries (z.B. «Wetter + EPG für heute Abend in Zürich»)
  erforderten zwei sequentielle Tool-Calls vom Client

Das Pattern ist für reine API-Wrapper grundsätzlich akzeptabel, eine
Aggregation reduziert für die naheliegende Tagesbriefing-Query aber Latenz
und Token-Verbrauch des Clients.

## Expected Behavior

Mindestens ein Aggregations-Tool sollte vorhanden sein, das die im Audit
explizit genannte Query («Wetter + EPG für heute Abend») abdeckt und die
Upstream-Calls parallelisiert (`asyncio.gather`), damit Clients nicht zwei
sequentielle Tool-Calls absetzen müssen.

## Remediation

Umgesetzt in `src/srgssr_mcp/server.py`:

### 1. Aggregation-Tool `srgssr_daily_briefing`

Ein neues Tool kombiniert SRF Meteo `24hour` mit `EPG /programs` und
parallelisiert die beiden Upstream-Calls:

```python
weather_result, epg_result = await asyncio.gather(
    _safe_api_get(f"{WEATHER_BASE}/24hour", params=weather_query),
    _safe_api_get(f"{EPG_BASE}/programs", params=epg_query, not_found_hint=epg_hint),
)
```

Eingaben (`DailyBriefingInput`): `business_unit`, `channel_id`, `date`
(YYYY-MM-DD), `latitude`, `longitude`, optional `geolocation_id`,
`response_format` ∈ {markdown, json}.

Ausgaben (markdown):

```markdown
# Tagesbriefing – SRF1 (SRF) am 2026-04-30

## Wetter (24h)
| Stunde | Temp °C | Niederschlag | Wetterlage |
| ... |

## TV-/Radioprogramm
**19:30** — Tagesschau
  Die Hauptausgabe der Nachrichten.
```

### 2. Graceful Degradation via `_safe_api_get`

Damit eine einzelne 4xx-Antwort die parallele Aggregation nicht abreissen
lässt, wurde `_safe_api_get` neben `_api_get` ergänzt:

```python
async def _safe_api_get(url, params=None, not_found_hint=None) -> dict | str:
    try:
        return await _api_get(url, params=params)
    except Exception as e:
        return _handle_error(e, not_found_hint=not_found_hint)
```

Schlägt eine der beiden Quellen fehl (z.B. 404 auf einer Bogus-`channel_id`),
rendert das Tool die intakte Sektion vollständig und ersetzt nur die
fehlgeschlagene Sektion durch die lokalisierte Fehlermeldung inkl.
Recovery-Hint (ARCH-003-Pattern wiederverwendet).

### 3. Refactor: EPG-Formatter extrahiert

Der vormals inline in `srgssr_epg_get_programs` enthaltene Markdown-Renderer
wurde nach `_format_epg_programs(programs, channel_id, bu, date)` ausgelagert
und wird vom neuen Aggregation-Tool wiederverwendet — kein Duplicate.

### 4. Tests

Vier neue Unit-Tests in `tests/test_unit.py` (Sektion *ARCH-007*):

| Test | Prüft |
|---|---|
| `test_daily_briefing_combines_weather_and_epg` | Markdown enthält beide Sektionen mit korrekt gerenderten Werten |
| `test_daily_briefing_runs_upstreams_in_parallel` | Beide Upstream-Calls sind gleichzeitig in-flight (peak concurrency = 2) |
| `test_daily_briefing_partial_failure_renders_remaining_section` | EPG-404 lässt Wetter-Sektion intakt; 404-Hinweis erscheint in EPG-Sektion |
| `test_daily_briefing_json_format_returns_both_payloads` | JSON-Output trägt `weather` und `epg` als getrennte Felder |

Damit existieren weiterhin nur thin-wrapper Tools für die einzelnen
Endpoints — die Composability-Kompromisse (mehr Komplexität pro Tool, mehr
Maintenance bei Schema-Änderungen) entstehen nur dort, wo eine Cross-Domain-
Query echten Nutzen bringt.

## Effort Estimate

**M** — ~2 Stunden (Tool + Helper-Refactor + 4 Tests + Doku).

## Verification After Fix

```bash
# asyncio-Aggregation existiert
grep -n "asyncio.gather" src/srgssr_mcp/server.py
# Erwartung: ≥ 1 Treffer in srgssr_daily_briefing

# Aggregation-Tool ist registriert
python -c "from srgssr_mcp.server import srgssr_daily_briefing; print(srgssr_daily_briefing.__name__)"
# Erwartung: srgssr_daily_briefing

# ARCH-007-Tests grün
pytest -m "not live" -k daily_briefing -v
# Erwartung: 4 Tests grün

# Voller Unit-Test-Lauf weiterhin grün
pytest -m "not live" -q
# Erwartung: 67 Tests grün (63 vorher + 4 neu)
```
