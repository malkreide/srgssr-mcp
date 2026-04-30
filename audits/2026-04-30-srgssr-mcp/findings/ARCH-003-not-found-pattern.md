# Finding: ARCH-003 — «Not Found» Anti-Pattern: Heuristiken statt leerer Antworten

| Feld | Wert |
|---|---|
| **Severity** | medium |
| **Status** | fixed |
| **Server** | `srgssr-mcp` |
| **Check-Reference** | `ARCH-003` |
| **PDF-Reference** | Sec 2.2 |
| **Audit-Datum** | 2026-04-30 |
| **Auditor** | Claude (mcp-audit-skill v0.5.0) |

## Observed Behavior

**Vor dem Fix:**
- `srgssr_weather_search_location` lieferte bei leerer Trefferliste eine
  einzeilige Fehlermeldung ohne Retry-Mechanismus (z.B. fehlte ein
  Diakritika-toleranter Fallback: «Zurich» traf nicht «Zürich»).
- Andere Tools (Video/Audio Episodes, EPG, Polis Votation Results) gaben bei
  einer 404 nur die generische Fehlermeldung «Fehler 404: Ressource nicht
  gefunden. Bitte ID oder Parameter prüfen.» zurück — ohne Hinweis, *welches*
  Listing-Tool zur Auflösung des Identifiers verwendet werden sollte.
- List-Tools (`srgssr_video_get_shows`, `…_audio_get_shows`, Livestreams,
  Polis-Listen) lieferten bei leerem Resultat nur eine leere Markdown-Liste
  ohne Erklärung oder Vorschlag.

## Expected Behavior

Suchwerkzeuge und ID-Lookups in nicht-sensiblen Domänen liefern bei leeren
Resultaten Heuristiken (Fuzzy-Match, normalisierte Retries) und Suggestions
für korrekte Eingaben oder weiterführende Tools.

## Remediation

Umgesetzt in `src/srgssr_mcp/server.py`:

### 1. Fuzzy-Match im Weather-Suchwerkzeug

`srgssr_weather_search_location` führt nun bei leerem Resultat automatische
Retries mit normalisierten Query-Varianten durch:

```python
def _query_variants(query: str) -> list[str]:
    # Original, ASCII-gefaltet, lowercase, Title-Case (dedupliziert)
```

Beispiel: `query="Zurich"` → API-Aufrufe mit `"Zurich"`, `"zurich"`, `"Zurich"`
(Title), bis ein Treffer kommt; in der Markdown-Antwort wird die erfolgreiche
Variante annotiert (`«… (Treffer via 'Zürich')»`). Bei finaler Leere listet die
Antwort alle versuchten Varianten und gibt konkrete Vorschläge (PLZ,
Diakritika, kürzerer Namensteil).

### 2. 404-Recovery-Hints für ID-Lookups

`_handle_error()` akzeptiert ab sofort einen optionalen `not_found_hint`,
der bei HTTP-404 angehängt wird. Konkret:

| Tool | 404 → Hinweis auf |
|---|---|
| `srgssr_video_get_episodes` | `srgssr_video_get_shows` |
| `srgssr_audio_get_episodes` | `srgssr_audio_get_shows` |
| `srgssr_polis_get_votation_results` | `srgssr_polis_get_votations` |
| `srgssr_epg_get_programs` | `srgssr_video_get_livestreams` / `…_audio_get_livestreams` |

### 3. Empty-Result-Hints für List-Tools

Bei leerer (nicht 404) Antwort liefern alle Listen-Tools nun strukturierte
Vorschläge:

- **shows / livestreams (Video & Audio):** Hinweis auf alternative Business
  Units und Pagination-Reset.
- **polis_get_votations / get_elections:** dynamische Filter-Suggestions
  (Canton-Filter weglassen, year_from/year_to ausweiten) — basierend auf den
  tatsächlich gesetzten Eingabewerten.

### 4. Tests

Zehn neue Unit-Tests in `tests/test_unit.py` (Sektion *ARCH-003*) decken ab:

- Fuzzy-Retry mit ASCII-Folding (Zürich/Zurich)
- All-empty-Suggestions im Weather-Tool
- 404-Recovery-Hints für video/audio episodes, votation_results, epg
- Empty-Result-Hints für video_get_shows und polis_get_votations/elections

## Effort Estimate

**S** — ~30 Minuten pro Tool, insgesamt ~3 Stunden inkl. Tests und Doku.

## Verification After Fix

```bash
# Helper-Funktion existiert und ist exportiert
grep -n "_query_variants" src/srgssr_mcp/server.py

# 404-Hinweise in allen ID-Lookup-Tools
grep -n "not_found_hint" src/srgssr_mcp/server.py | wc -l
# Erwartung: ≥ 4 (video_get_episodes, audio_get_episodes,
#                  polis_get_votation_results, epg_get_programs)

# ARCH-003-Tests grün
pytest -m "not live" -k arch_003 or fuzzy or recovery -v
# Erwartung: alle ARCH-003-Tests grün
```
