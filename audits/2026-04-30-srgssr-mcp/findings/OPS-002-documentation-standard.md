# Finding: OPS-002 — Doku-Standard: bilingualer README, ASCII-Diagramm, Limits-Sektion

| Feld | Wert |
|---|---|
| **Severity** | medium |
| **Status** | fixed |
| **Server** | `srgssr-mcp` |
| **Check-Reference** | `OPS-002` |
| **PDF-Reference** | Anhang C2 |
| **Audit-Datum** | 2026-04-30 |
| **Auditor** | Claude (mcp-audit-skill v0.5.0) |

## Observed Behavior

**Vorhanden (✓):**
- Bilingualer README (EN/DE)
- Anchor Demo Query vorhanden
- Installation, Features, Prerequisites dokumentiert

**Fehlt:**
- ASCII/Mermaid Architecture Diagram
- «Known Limits»-Sektion

## Expected Behavior

**Architecture Diagram:**
```markdown
## Architecture

┌─────────────┐
│ Claude / LLM│
└──────┬──────┘
       │ MCP (stdio)
┌──────▼───────────────────┐
│ srgssr-mcp Server        │
│  ├─ Weather Tools (4)    │
│  ├─ EPG Tools (1)        │
│  ├─ Polis Tools (3)      │
│  ├─ Video Tools (3)      │
│  └─ Audio Tools (3)      │
└──────┬───────────────────┘
       │ HTTPS (OAuth2)
┌──────▼──────────────┐
│ SRG SSR Public APIs │
│  developer.srgssr.ch│
└─────────────────────┘
```

**Known Limits:**
```markdown
## Known Limits

- **Rate Limits:** SRG SSR APIs haben Rate-Limits (Details bei developer.srgssr.ch)
- **Data Freshness:** EPG-Daten sind bis zu 6 Stunden verzögert
- **Historical Data:** Polis-Daten reichen bis 1900, ältere Daten nicht verfügbar
- **Geo-Restriction:** Einige Streaming-APIs nur in der Schweiz verfügbar
```

## Effort Estimate

**S** — < 1 Tag für Dokumentations-Ergänzung.

## Remediation

Umgesetzt in:
- `README.md` — Architecture-Diagramm auf Tool-Cluster-Layout umgestellt, «Known Limits»-Sektion hinzugefügt
- `README.de.md` — analoge Änderungen mit deutschsprachigen Cluster-Labels und «Bekannte Limits»-Sektion
- `CHANGELOG.md` — Eintrag im «Unreleased»-Block

## Verification After Fix

```bash
# Architecture-Block enthält Tool-Cluster
grep -E "Weather Tools \(4\)" README.md
grep -E "Wetter-Tools \(4\)" README.de.md

# Known-Limits-Sektion vorhanden
grep -E "^## Known Limits" README.md
grep -E "^## Bekannte Limits" README.de.md

# Alle vier Limit-Items dokumentiert
grep -E "Rate Limits|Data Freshness|Historical Data|Geo-Restriction" README.md
```
