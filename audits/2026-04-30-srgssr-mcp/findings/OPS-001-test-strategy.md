# Finding: OPS-001 — Test-Strategie: Unit-Tests mocked + Live-Tests gemarkert

| Feld | Wert |
|---|---|
| **Severity** | high |
| **Status** | open |
| **Server** | `srgssr-mcp` |
| **Check-Reference** | `OPS-001` |
| **PDF-Reference** | Anhang C1 |
| **Audit-Datum** | 2026-04-30 |
| **Auditor** | Claude (mcp-audit-skill v0.5.0) |

## Observed Behavior

Der Server hat **kein `tests/`-Verzeichnis** und keine Test-Suite.

**Automatisierte Prüfung:**
```bash
ls tests/
# Output: ls: cannot access 'tests/': No such file or directory

test -f tests/test_unit.py && echo "✓ unit" || echo "✗ unit MISSING"
# Output: ✗ unit MISSING
```

**Keine Tests vorhanden:**
- Keine Unit-Tests mit HTTP-Mocking (respx)
- Keine Live-Tests gegen echte SRG SSR APIs
- Keine CI-Integration für automatisierte Tests
- Keine Regression-Detection bei Code-Änderungen

**Evidence-File:** `audits/2026-04-30-srgssr-mcp/raw/OPS-001.txt`

## Expected Behavior

Best-Practice-Katalog verlangt **zwei Test-Kategorien mit klarer Trennung:**

| Kategorie | Zweck | Wann ausgeführt | Mock | Speed |
|---|---|---|---|---|
| **Unit-Tests** | Server-Logik isoliert prüfen | CI bei jedem PR | respx-mocked HTTP | ~1s pro Test |
| **Live-Tests** | Echte API-Antworten gegen aktuelle Schnittstellen prüfen | Manuell, nightly, vor Release | keiner | 5-30s pro Test |

**Verzeichnis-Layout:**
```
tests/
├── test_unit.py         # respx-mocked, schnell, CI-safe
├── test_live.py         # echte APIs, langsam, @pytest.mark.live
├── conftest.py          # shared fixtures
└── __init__.py
```

**pyproject.toml:**
```toml
[tool.pytest.ini_options]
markers = [
    "live: tests against real APIs (manual, nightly only)",
]
```

**CI-Workflow (`.github/workflows/test.yml`):**
```yaml
- name: Run unit tests (no live)
  run: pytest -m "not live" --cov=src --cov-report=term-missing
```

**Separater nightly Live-Test-Workflow:**
```yaml
# .github/workflows/live-test.yml
on:
  schedule:
    - cron: "0 4 * * *"  # nightly 04:00 UTC
  workflow_dispatch:

jobs:
  live-tests:
    runs-on: ubuntu-latest
    steps:
      - run: pytest -m live
```

## Evidence

**tests/-Verzeichnis fehlt:**
```bash
find . -type d -name tests
# Output: (leer)
```

**Keine Test-Dependencies in pyproject.toml:**
```bash
grep -E "pytest|respx" pyproject.toml
# Output: (vermutlich leer, nicht im Raw-Output dokumentiert)
```

**Keine CI-Workflows:**
```bash
ls .github/workflows/
# (Status unbekannt, vermutlich keine Test-Workflows)
```

## Risk Description

Ohne strukturierte Test-Strategie entstehen folgende kritische Risiken:

### 1. Regressionen unbemerkt
**Szenario:** Maintainer ändert API-URL oder Daten-Transformation
- Keine Tests → Fehler werden erst von Usern gemeldet
- Breaking Changes gehen unbemerkt in Production

### 2. Refactoring unsicher
- Code-Verbesserungen sind riskant ohne Confidence
- Maintainer vermeiden notwendige Änderungen aus Angst vor Bruch

### 3. API-Schema-Drift unentdeckt
SRG SSR APIs können Schema-Änderungen machen.
→ Ohne Live-Tests: Drift wird erst bemerkt, wenn User sich beschweren.

### 4. CI-Pipeline fehlt
- Kein automatisiertes Testen bei PRs
- Maintainer müssen manuell testen

### 5. Contributor-Barriere
- Neue Contributors können nicht verifizieren dass ihre Änderungen funktionieren

**Severity high:** Keine akute Sicherheitslücke, aber **kritische Lücke für Wartbarkeit und Produktionsreife**.

## Remediation

Siehe Implementierung in:
- `pyproject.toml` (Dependencies + pytest-Konfiguration)
- `tests/conftest.py` (Shared Fixtures)
- `tests/test_unit.py` (respx-mocked Unit-Tests)
- `tests/test_live.py` (Live-Tests gegen echte APIs)
- `.github/workflows/test.yml` (Unit-Test-CI)
- `.github/workflows/live-test.yml` (Nightly Live-Tests)

## Effort Estimate

**M** — 1-3 Tage Initial-Setup

## Verification After Fix

```bash
# Verzeichnis-Check
ls tests/
# Erwartung: test_unit.py, test_live.py, conftest.py

# Unit-Test-Run
pytest -m "not live" -v
# Erwartung: 14 Tools × 3 Tests = 42 Tests grün

# Live-Test-Run (manuell, mit Credentials)
export SRGSSR_CONSUMER_KEY=...
export SRGSSR_CONSUMER_SECRET=...
pytest -m live -v
# Erwartung: 14 Tests grün

# Coverage-Check
pytest -m "not live" --cov=src --cov-report=term-missing
# Erwartung: Coverage > 80%
```
