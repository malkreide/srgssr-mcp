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
