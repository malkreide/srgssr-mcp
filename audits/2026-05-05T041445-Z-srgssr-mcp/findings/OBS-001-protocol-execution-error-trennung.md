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
