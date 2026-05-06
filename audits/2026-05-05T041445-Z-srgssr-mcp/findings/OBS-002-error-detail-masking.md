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
