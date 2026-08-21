# CLAUDE.md

## Teil 1 — Konventionen (portfolio-weit)

### Vor der Arbeit

Klon-Aktualität prüfen — Standard-Branch ermitteln, nicht `main` annehmen:

```bash
B=$(git ls-remote --symref origin HEAD | sed -n 's|^ref: refs/heads/\([^[:space:]]*\).*|\1|p')
git fetch origin "${B:?Standard-Branch nicht ermittelbar}" &&
  git rev-list --count HEAD..FETCH_HEAD
```

Drei Server im Portfolio heissen ihren Standard-Branch `master`
(`openlex-mcp`, `swiss-courts-mcp`, `swisstopo-mcp`); dort scheitert ein fest
verdrahtetes `origin/main` mit «couldn't find remote ref main». Wer das für ein
Netzproblem hält, arbeitet weiter auf genau dem veralteten Klon, vor dem dieser
Absatz warnt. Den `:?`-Schutz nicht weglassen: Bei leerem `B` fetcht git still
den Remote-HEAD und endet mit 0.

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

### Wenn zwei Agenten dasselbe tun

Vor dem Anlegen eines Branches mit vorgegebenem Namen prüfen, ob es ihn schon
gibt:

```bash
git ls-remote --heads origin claude/<name> | wc -l
```

Steht dort `1`, arbeitet jemand anderes daran — mit Schreibrecht auf denselben
Ref.

Ein PR mit leerem Diff wird geschlossen, nicht gemergt. Der Test ist
`get_files` auf dem PR: kommt `[]` zurück, ändert er nichts. Ein grüner Check
sagt dazu nichts — die CI prüft den Head, nicht die Differenz zur Basis.

Am 21.8.2026 liefen zwei Sessions dieselbe Aufgabe über 45 Repos, auf den
Branches `claude/codex-review-audit-templates-9sn6mx` und
`claude/codex-review-audit-7ioh56`. Wo die eine zuerst nach `main` kam, wurde
`main` in den Branch der anderen gemergt und der add/add-Konflikt zugunsten
von `main` aufgelöst. Übrig blieben 14 PRs, die durch sämtliche Gates grün
liefen und nichts enthielten; sie wurden gemergt und hinterliessen leere
Merge-Commits. Mit den zwei Folge-PRs, die aus demselben Grund gegenstandslos
waren, waren 16 der 59 PRs jenes Tages reine Reibung.

Dieselbe Klasse wie der handgeschriebene Stub, der denselben Feldnamen annahm
wie der Code: Nichts ist rot, weil nichts geprüft wird, worauf es ankommt.

## Teil 2 — dieses Repo

**ruff:** genau eine Quelle — `ruff==0.16.1` im `[dev]`-Extra von
`pyproject.toml`. `pip install -e ".[dev]"` reicht also, lokal wie in der CI.
Keine zweite Version in die Workflows schreiben: ein solcher Schritt läuft
nach dem `[dev]`-Install und überstimmt den Pin still (`test_dependencies.py`
hält beides fest). Eine `.pre-commit-config.yaml` gibt es nicht.

Vor dem Lauf `ruff --version` prüfen: ein älteres ruff früher im `PATH`
schlägt den Pin, ohne dass der Install etwas meldet.

**Gates, wörtlich aus der CI:**

```bash
python scripts/check_ruff_pin.py
ruff check src/ tests/ scripts/
ruff format --check src/ tests/ scripts/
python -m py_compile src/srgssr_mcp/server.py
python scripts/check_version_sync.py
pytest -m "not live" --cov=src --cov-report=term-missing --cov-fail-under=80
```

**«Die CI» sind hier zwei Workflows.** Die ersten vier Befehle stehen im Job
`quality` in `ci.yml`, der `pytest` allein im Job `test` in `test.yml` —
beide mit Matrix 3.11/3.12/3.13, beide auf `push`/`pull_request` gegen `main`.
Ein roter Check «CI» und ein roter Check «Tests» zeigen also auf verschiedene
Dateien; wer nach dem falschen sucht, findet nichts. In `test.yml` trägt der
`pytest` zusätzlich `--cov-report=xml` für den Upload danach — der Upload ist
auf 3.11 beschränkt und `continue-on-error: true`, also kein Gate. Das
Coverage-Minimum von 80 % ist eines: es steht im `pytest`-Aufruf selbst.

**`secret-scan.yml` gatet ebenfalls jeden PR** (gitleaks, gegen `main`) und
steht in keiner Liste — lokal stellt ihn keiner der Befehle oben nach. Ein
roter PR bei grünen Tests ist meistens er.

Kein `include` unter `[tool.ruff]` setzen. Es stand dort auf
`["src/**/*.py"]` und hob die Pfadangabe der beiden ruff-Gates still wieder
auf: sie liefen grün, während sie nur `src/` prüften (behoben in #68).

**Fixtures: der Recorder steht, die Aufzeichnungen fehlen noch.** Die Messung
vom 15.08.2026 stimmt — ohne Consumer Key antworten Token-Endpunkt und alle
fünf Produkt-Basen mit 401 —, aber die Schlussfolgerung daraus war zu weit.
Nachgemessen am 16.08.2026: die 401 kommt von SRG SSR selbst (eigene Header,
CONNECT geht durch), der Host ist also erreichbar und es fehlen allein die
Credentials. Die liegen längst da, wo der nächtliche Live-Lauf sie nimmt.
`.github/workflows/record-fixtures.yml` fährt `scripts/record_fixtures.py` mit
denselben Secrets, auf Knopfdruck.

Ein Recorder, den niemand fahren *und* niemand prüfen kann, wäre das plausibel
aussehende, unwiderlegbare Artefakt, gegen das die Konvention gerichtet ist.
Seine Mechanik hängt aber nicht an den Credentials:
`tests/test_record_fixtures.py` fährt ihn gegen eine gemockte API und prüft
Plan, Zuordnung, Kürzung, Nachweis — und vor allem den Token-Umgang.

**Das Token gehört in keine Datei.** Diese API ist die einzige im Portfolio mit
OAuth2. Die Antwort von `/oauth/v1/accesstoken` trägt ein gültiges
Bearer-Token, die Anfrage dorthin `Authorization: Basic <key:secret>`. Ein
Recorder, der «jede Antwort» ablegt, committet beim ersten Lauf ein
funktionierendes Token. Drei Riegel: die Token-URL ist ausgenommen, der
Schlüssel ist die URL ohne jeden Header, und vor dem Schreiben läuft eine
Prüfung gegen Token, Key und Secret, die **abbricht** statt zu warnen — eine
halb geschriebene Aufzeichnung ist wiederholbar, ein veröffentlichtes Token
nicht. Der Workflow prüft danach noch einmal, ausserhalb des Programms, das er
bewacht.

**`srf-meteo` drosselt hart.** Gemessen: der zweite Abruf auf dieselbe
Koordinate kommt mit HTTP 429 zurück und bleibt es über vier Retries. Vier
Werkzeuge lösen dieselbe Koordinate auf, der Recorder holt sie deshalb genau
einmal (`_EinmalHolen`) und pausiert zwischen den Plan-Einträgen. Wer den
Aufnahme-Workflow zweimal kurz hintereinander fährt, misst die Drosselung und
nicht die Quelle — nach einem roten Lauf erst warten, dann wiederholen.

Bis die Aufzeichnungen da sind, trägt der nächtliche Live-Lauf die Drift-Frage
— stärker als Fixtures, weil er die Quelle von heute prüft, aber nur solange er
*jedes* Werkzeug erreicht. Genau das hält `test_live_coverage.py` fest, samt
der Probe im Docstring.

**Live-Tests:** `.github/workflows/live-test.yml` läuft nächtlich per Cron
(`0 4 * * *`) plus `workflow_dispatch`, mit Credential-Guard vor dem Lauf; ein
roter Lauf öffnet ein Issue, der von Hand gestartete ebenso. Sie sind hier also
nicht bloss per `-m "not live"` ausgeschlossen. Der Workflow allein erfüllt
DRIFT-005 aber nicht — dazu gehört, Kadenz und Empfänger zu dokumentieren, und
das steht in `CONTRIBUTING.md`, gegen den Workflow gehalten von
`test_live_workflow_docs.py`.
