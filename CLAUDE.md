# CLAUDE.md

## Teil 1 — Konventionen (portfolio-weit)

### Vor der Arbeit

Klon-Aktualität prüfen: `git fetch origin main && git rev-list --count HEAD..origin/main`
Ein veralteter Klon erzeugt eine rote CI, deren Ursache nicht im Diff steht.
Am 3.8.2026 zweimal passiert — beide Male fehlten genau die Commits, die
das Gate einführten, an dem der Branch scheiterte.

Gates lokal fahren, mit der GEPINNTEN ruff-Version aus der CI. Eine andere
Version meldet Abweichungen, die niemand verursacht hat.

### Tests

Gegenprobe ist Pflicht. Ein Test, der grün bleibt, wenn man die
Implementierung entfernt, prüft nichts. Jede neue Zusicherung einzeln
neutralisieren und zeigen, dass genau die zugehörigen Tests fallen.

Zwei Fallen, die beide grün blieben:

- Eine Fake-Uhr, die nur beim Schlafen vorrückt, kann eine Zusicherung über
  echte Zeit nicht widerlegen.
- `monkeypatch.setattr(modul.asyncio, "sleep", ...)` greift ins Modul
  `asyncio` selbst und entschärft die Mechanik im ganzen Prozess. Patche
  einen Modul-Alias (`_sleep = asyncio.sleep`), nicht das fremde Modul.

Handgeschriebene Fixtures kodieren die Annahme des Autors und können sie
nicht widerlegen. Mindestens eine aufgezeichnete Antwort pro externem
Endpunkt, mit Aufnahmedatum.

### Wenn etwas rot ist

Roter Live-Test: erst die Quelle abfragen, dann einordnen. Nicht aus der
Fehlermeldung schliessen. Am 3.8.2026 hiess "nicht gefunden" nicht, dass der
Datensatz weg war, sondern dass die Quelle die Schreibweise ihrer Kopfzeile
gewechselt hatte — vier von sechs Datensätzen produktiv kaputt, alle
Unit-Tests grün.

PR ohne jeden Check ist selten ein Repo ohne CI, meistens ein
Merge-Konflikt: GitHub berechnet dafür keinen Merge-Commit und startet nichts.

Ein Codex-Review auf einem PR wird beantwortet oder behoben, nie ignoriert.

## Teil 2 — dieses Repo

**ruff:** genau eine Quelle — `ruff==0.16.1` im `[dev]`-Extra von
`pyproject.toml`. `pip install -e ".[dev]"` reicht also, lokal wie in der CI.
Keine zweite Version in die Workflows schreiben: ein solcher Schritt läuft
nach dem `[dev]`-Install und überstimmt den Pin still (`test_dependencies.py`
hält beides fest). Eine `.pre-commit-config.yaml` gibt es nicht.

**Gates, wörtlich aus der CI:**

```bash
ruff check src/ tests/ scripts/
ruff format --check src/ tests/ scripts/
python -m py_compile src/srgssr_mcp/server.py
python scripts/check_version_sync.py
pytest -m "not live" --cov=src --cov-report=term-missing --cov-fail-under=80
```

Kein `include` unter `[tool.ruff]` setzen. Es stand dort auf
`["src/**/*.py"]` und hob die Pfadangabe der beiden ruff-Gates still wieder
auf: sie liefen grün, während sie nur `src/` prüften (behoben in #68).

**Live-Tests:** `.github/workflows/live-test.yml` läuft nächtlich per Cron
(`0 4 * * *`) plus `workflow_dispatch`, mit Credential-Guard vor dem Lauf; ein
roter Lauf öffnet ein Issue, der von Hand gestartete ebenso. Sie sind hier also
nicht bloss per `-m "not live"` ausgeschlossen. Der Workflow allein erfüllt
DRIFT-005 aber nicht — dazu gehört, Kadenz und Empfänger zu dokumentieren, und
das steht in `CONTRIBUTING.md`, gegen den Workflow gehalten von
`test_live_workflow_docs.py`.
