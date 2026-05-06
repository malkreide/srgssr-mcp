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
