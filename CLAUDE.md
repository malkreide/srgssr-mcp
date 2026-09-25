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

**Ein 4xx ist kein Nein.** Am 29.8.2026 antwortete `past-publications` in
`swiss-procurement-mcp` auf jede Publikation mit Losen mit HTTP 400. Daraus war
geschlossen worden, die Quelle verweigere diese Auskunft; der Befund stand
datiert im Fixture-Nachweis, ein Test bestätigte ihn, alles blieb grün. Die
Spec desselben Endpunkts führt einen als *optional* deklarierten Parameter
`lotId` — für Publikationen mit Losen ist er Pflicht. Mit ihm antwortet
dieselbe Publikation mit 200. Ein Projekt trug sieben Vorgängerpublikationen,
die der Server als «Quelle nicht erreichbar» wegwarf.

Drei Handgriffe daraus:

- **Die Parameterliste der Spec durchgehen, bevor ein Statuscode eingeordnet
  wird.** «Optional» heisst dort oft «optional für die Mehrheit».
- **Einer deterministischen Absage keinen Wiederholungsrat geben.** «Nicht
  erreichbar, bitte später erneut» ist bei einem 400 falsch und liest sich für
  das Modell wie eine Störung. Den Status mitführen und den fehlenden
  Parameter benennen — den Status, nicht den Antwortkörper.
- **Beide Antworten aufzeichnen, mit und ohne den Parameter.** Eine
  Aufzeichnung nur des Fehlschlags kann nicht zeigen, dass er vermeidbar war;
  dass nur der 400er aufgezeichnet war, ist der Grund, warum der falsche
  Befund nicht auffiel.

**Und ein 403 ist gar keine Auskunft.** Am 29.8.2026 sollten für 42 Repos die
Dependabot-Labels nachgemessen werden. Alle 13 Abfragen des ersten Stapels
kamen zurück als:

```
Failed to find label: API rate limit already exceeded for user ID 8864492.
```

Der gefährliche Teil steht vorn: Das Werkzeug verpackt eine Sperre als
Fund-Fehlschlag. Wer die Zeile überfliegt oder nur auf ein leeres Ergebnis
prüft, zählt 39 Repos als «Label fehlt» und hat seine eigene Erschöpfung
gemessen. Das Limit hängt am Konto, nicht am Repo — derselbe Vormittag hatte
es mit 42 eröffneten und 42 gemergten PRs verbraucht.

Das ist der Absatz darüber, andersherum gelesen: dort war ein 400 eine echte,
wiederholbare Antwort und galt als Störung; hier ist eine Störung als Antwort
verpackt. Entscheidend ist nie der Statuscode, sondern ob die Quelle überhaupt
geantwortet hat.

- **Positivkontrolle im selben Repo.** Ein «nicht gefunden» wird erst dadurch
  zur Messung, dass eine gleichzeitige Abfrage etwas findet.
- **Die Messung entlang der Sperre teilen.** `raw.githubusercontent.com` ist
  ein CDN und nicht die REST-API. Um 11:19:27 UTC lieferte es für
  `register-mcp` HTTP 200, während die Label-Abfrage desselben Repos in
  derselben Minute die Sperre meldete. Alle 42 `dependabot.yml` kamen so
  durch, während die Label-Hälfte stand.
- **Am Token vorbei geht es nicht.** Beide Umwege enden am Agent-Proxy, und
  jeder mit einer eigenen irreführenden Begründung. `api.github.com` ohne
  Zugangsdaten:

  ```
  GitHub access is not enabled for this session. An org admin must connect
  the Claude GitHub App for this organization.
  ```

  Das ist keine Aussage über die Organisation, sondern das, was ohne Token
  kommt. Wer ihr folgt, sucht einen Admin für ein Problem, das keiner hat.
  Die HTML-Seite `github.com/<owner>/<repo>/labels` fällt ebenfalls, aber
  anders:

  ```
  This GitHub API path is not available: sessions are bound to their
  configured repositories. Use repository-scoped endpoints
  (repos/{owner}/{repo}/...).
  ```

  Der Proxy behandelt also auch `github.com` als API-Pfad; die zweite Meldung
  klingt nach einem Scope-Problem und ist doch nur dieselbe Sackgasse. Den
  Token aus der Umgebung in einen curl-Header zu setzen, blockiert der
  Klassifikator. Ob es überhaupt hülfe, ist offen: die Sperre nennt ein
  Nutzerkonto, und ob der Token zu diesem gehört, wurde nie geprüft.
- **Die Sperre gilt nicht dem Dienst, sondern dem Zugangspfad.** Unmittelbar
  nachdem eine Abfrage der Checks eines PR sauber durchlief, meldete die
  Label-Abfrage weiter die Sperre. Von einem blockierten Werkzeug also nicht
  auf «GitHub ist zu» schliessen — und umgekehrt eine gelungene Abfrage nicht
  als Entwarnung für die gesperrte nehmen.

Wann die Sperre fällt, geben diese Beobachtungen nicht her. Die Meldung nennt
keinen Zeitpunkt, und die `X-RateLimit`-Kopfzeilen sind hinter dem Proxy nicht
zu sehen. Belegt sind drei gesperrte Zeitpunkte — 11:14, 11:16 und 11:19 UTC.
Wer daraus eine Dauer macht, hat sie erfunden.

**Dieselbe Falle bei einer Konfigurationsoption: die Vorgabe lesen, bevor man
einen Schlüssel für wirkungslos hält.** Am 29.8.2026 fielen die
`labels:`-Zeilen aus den `dependabot.yml` des Portfolios, begründet mit
«Dependabot legt Labels nicht an». Eine Messung danach zeigte, dass
`dependencies` in 36 von 42 Repos sehr wohl existiert, 35 davon mit GitHubs
Standardbeschreibung. Das las sich zuerst wie ein Beleg, dass die Aktion
falsch war.

Die Optionsreferenz kehrt es um:

```
Dependabot creates these default labels automatically, as necessary in
your repository.

If you define more than one package manager, an additional label for the
ecosystem or language is added to each pull request.

The labels specified are used instead of the default labels.
```

Ohne `labels:` vergibt Dependabot also `dependencies` — und, sobald mehr als
ein Paketmanager deklariert ist, zusätzlich ein Ökosystem-Label — und legt sie
selbst an; eine eigene Liste **ersetzt** diesen Satz, und «if any of these
labels is not defined in the repository, it is ignored». Die Zeile war nicht
wirkungslos — sie tauschte einen sich selbst pflegenden Vorgabesatz gegen eine
starre Liste.

**Die Bedingung nicht weglassen.** Bei nur einem Paketmanager steht das
Ökosystem-Label gar nicht zu; wer es dort trotzdem erwartet, schreibt genau
den Fehlbefund auf, gegen den dieser Abschnitt geschrieben ist — der Abschnitt
liefe an sich selbst vorbei. Im Portfolio deklariert jede `dependabot.yml`
zwei (`pip` und `github-actions`), die Bedingung ist hier also überall
erfüllt; anderswo nicht unbedingt. Aufgefallen ist die fehlende Bedingung
nicht beim Schreiben, sondern durch einen Codex-Review auf
`swiss-environment-mcp` PR #113 — vierzehn Sekunden vor dem Merge desselben
PR.

Was das kostet, ist an `openlex-mcp` gemessen: zwei Ökosysteme deklariert,
also stünden `dependencies` **und** ein Ökosystem-Label zu; vorhanden ist nur
das erste, `github-actions` und `github_actions` fehlen beide (Kontrolle `bug`
vorhanden). `register-mcp` ist die Gegenprobe: dort existieren alle vier
deklarierten Namen mit handgeschriebener Beschreibung, die Liste ist gewollt
und vollständig.

**Dreimal falsch eingeordnet, in drei Richtungen.** Erst die Zeile für bloss
wirkungslos gehalten. Dann die gefundenen Labels für einen Widerspruch. Dann,
auf denselben Fund gestützt, einen richtigen PR geschlossen mit dem Argument,
das Label existiere ja — obwohl es existiert, *weil* die Vorgabe es anlegt.
Der dritte Fehler ist der teuerste, weil er wie eine Messung aussah.

Was die Messung **nicht** hergibt: wer die 36 Labels angelegt hat. Die
Referenz sagt, Dependabot tue es; die Objekt-IDs liegen aber so dicht
beieinander, dass sie eher aus einem Stapellauf stammen. Beides passt zum
Befund, keines ist belegt — die Herkunft blieb ungemessen.

Beim Aufräumen gilt deshalb dieselbe Frage wie bei `lotId`: Was ist die
*Vorgabe*, wenn man das Ding weglässt — nicht bloss, ob der aktuelle Wert
etwas bewirkt.

**`results[0]` ist nur so verlässlich wie die Zusicherung danach.** Pinnt die
Abfrage einen bekannten Datensatz, ist der erste Treffer eine Drift-Wache und
in Ordnung. Hängt die Zusicherung dagegen davon ab, *welche* Variante die
Quelle heute zuoberst hat, prüft der Test den Tag: am 25.8.2026 rot, weil die
neueste Zürcher Publikation zufällig Lose hatte, am 26.8. grün, ohne dass sich
etwas geändert hätte. Den Fall gezielt wählen und beide Zweige fahren.

PR ohne jeden Check ist selten ein Repo ohne CI, meistens ein
Merge-Konflikt: GitHub berechnet dafür keinen Merge-Commit und startet nichts.

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

### Wenn ein Required Check den Merge nicht hält

Am 18.9.2026 bekamen alle 43 Repos des Portfolios Branch Protection auf ihrem
Standard-Branch: Required Status Checks, `strict = false`, `enforce_admins`,
keine Review-Pflicht. Für `srgssr-mcp` und `openlex-mcp` war vorher gemessen,
dass `main` ungeschützt war (`protected: false`) — ein grüner PR war sofort
mergebar, und GitHub bot deshalb nicht einmal Auto-Merge an. Das ist die Lücke,
durch die am 29.8. zwei Codex-Reviews vollständig auf bereits geschlossenen PRs
liefen. Für die übrigen 41 ist der Zustand davor **nicht** gemessen: das Skript
überschreibt, ohne vorher zu lesen.

Die Kontexte wurden nicht geraten, sondern am Head des jüngsten gemergten PR
gemessen — am Push-Head des Standard-Branches fehlen genau die Checks, die nur
auf `pull_request` triggern. Dagegen stand eine zweite, unabhängig gewonnene
Liste, abgeleitet aus den Workflow-Dateien. Die vier Repos, in denen beide
auseinandergingen, trugen vier verschiedene Fehler — und zwar in beiden
Quellen.

**Zwei Arten von Bedingung, und nur eine ist harmlos.** Ein Job, den ein `if:`
auf **Job**-Ebene überspringt, meldet laut GitHub-Dokumentation «skipped», und
das zählt für Branch Protection als bestanden. Ein Workflow, den ein `paths:`
auf **Workflow**-Ebene gar nicht erst startet, meldet nichts — sein Check
bleibt auf `pending`, und als Required Check blockiert er jeden PR dauerhaft,
der die Pfade nicht berührt. Betroffen waren `image-size`
(`swiss-environment-mcp`), `build & smoke-test` (`bakom-mcp`) und `nachziehen`
(`hn-tech-signal-mcp`); harmlos sind dagegen die vier `live`-Jobs mit
`if: github.event_name == 'schedule' || …` und `review-abgeschlossen` in diesem
Repo. Die Ableitung las die Job-Namen und übersah die Pfadfilter — sie hätte
drei Repos stillgelegt.

Dass ein übersprungener Job als bestanden zählt, stand hier zuerst nur als
Dokumentationsbehauptung. Gemessen ist es seit PR #122 in diesem Repo:
`review-abgeschlossen` ist dort Required Check und stand als Draft-PR auf
`skipped`. Um 13:55:32 UTC war der PR `blocked` — da liefen die drei
`test`-Jobs noch; um 13:58:50 UTC waren alle acht Checks fertig, sieben
`success` und einer `skipped`, und `mergeable_state` stand auf `clean`. Der
übersprungene hat also zu keinem Zeitpunkt blockiert.

Was die Messung **nicht** hergibt: dass dasselbe für einen pfadgefilterten
Workflow gälte. Dort entsteht gar kein Check-Run; dieser Fall wurde bewusst
nicht ausprobiert, weil ein Repo mit dem Versuch dauerhaft blockiert wäre.

**Eine Messung am jüngsten PR ist eine Momentaufnahme, keine Eigenschaft des
Repos.** `swiss-environment-mcp` lieferte am 18.9. innerhalb von zwei Stunden
drei verschiedene Antworten: im Trockenlauf PR #114 (ändert nur `CLAUDE.md`, 6
Kontexte), zehn Minuten später beim Anwenden PR #116 (fasst `src/**` an, also
lief `image-size` mit, 7 Kontexte), danach PR #117 mit einem umbenannten
Codex-Job. Die Gegenprobe hat alle drei Male gehalten. Ohne sie wäre beim
zweiten Lauf ein pfadgefilterter Check erforderlich geworden.

Daraus folgt auch: Ein sauberer Trockenlauf ist keine Freigabe für ein späteres
`-Apply`. Zwischen beiden Läufen kann gemergt werden, und dann misst der zweite
etwas anderes als der erste.

**`check-runs` sind nicht alle Checks.** GitHub führt zwei getrennte
Mechanismen, und `repos/{o}/{r}/commits/{sha}/check-runs` liefert nur den
neueren. Commit-Status der älteren Status-API stehen unter
`commits/{sha}/status` und tauchen dort überhaupt nicht auf. Im Portfolio
tragen genau zwei Repos ihr Codex-Urteil in einem Commit-Status `codex-gate`
(`fedlex-mcp`, `swiss-environment-mcp`); der Check-Run des zugehörigen Jobs
endet dort immer mit 0 und sagt nichts aus. `register-mcp` macht es
andersherum — dort endet der Job selbst rot, sein Check-Run **ist** das Gate.
Wer nur `check-runs` misst, schützt die ersten beiden ohne ihr eigentliches
Gate; `fedlex-mcp` stand rund vierzig Minuten genau so da.

**Die Rückleseprobe fängt das nicht.** Sie vergleicht, was gesendet wurde, mit
dem, was ankam — sie kann nicht wissen, dass zu wenig gesendet wurde. Neben
zwei unvollständigen Listen stand deshalb ein grünes «gesetzt und verifiziert».
Aufgefallen ist es nur, weil in `swiss-environment-mcp` zufällig am selben Tag
ein Job umbenannt wurde und die Abweichung zwang, in die Workflow-Datei zu
sehen; dort stand der Hinweis ausgeschrieben.

**Ein Repo ausserhalb der Liste wird nicht nachgezogen.** `srgssr-mcp` und
`openlex-mcp` waren am Vormittag von Hand gesetzt worden und standen deshalb
nicht in der Repo-Liste des Skripts. In `srgssr-mcp` kam danach
`codex-gate.yml` dazu (angelegt 18.9.2026, 04:11 UTC) und mit ihm der Kontext
`review-abgeschlossen` — den konnte die Konfiguration von Hand nicht kennen.
Ein von Hand gesetzter Schutz altert still; er wird nicht rot, wenn ein Gate
dazukommt.

**Beide Quellen behalten.** Die Versuchung nach einem sauberen Trockenlauf ist,
die Ableitung als erledigt wegzuwerfen und beim Anwenden nur noch zu messen.
Genau dann fällt keiner der vier Fehler mehr auf: Die Messung schleppt
bedingte Checks ein, die Ableitung übersieht Pfadfilter, und keine der beiden
sieht die andere Hälfte der API. Erst der Widerspruch ist die Prüfung.

## Teil 2 — dieses Repo

**ruff:** genau eine Quelle — das `[dev]`-Extra von `pyproject.toml`.
`pip install -e ".[dev]"` zieht die gepinnte Version, `ruff --version` zeigt
sie, und `scripts/check_ruff_pin.py` hält beides gegeneinander.
Keine zweite Version in die Workflows schreiben: ein solcher Schritt läuft
nach dem `[dev]`-Install und überstimmt den Pin still (`test_dependencies.py`
hält beides fest). Eine `.pre-commit-config.yaml` gibt es nicht.

**Die Nummer steht hier absichtlich nicht mehr**, und das ist an einem
Nachmittag zweimal teuer geworden. Hier stand `0.16.3`, während
`pyproject.toml` schon `0.16.4` pinnte — eine stille Drift, gefunden beim
Installieren nach dieser Zeile. Der naheliegende Handgriff war, die Zahl zu
korrigieren und einen Test daneben zu setzen, der sie gegen `pyproject.toml`
hält. Beides ging in #114 ein, und der nächste Dependabot-Bump
(0.16.4 → 0.16.5) kam **drei Minuten später** und machte mit diesem Test
`main` rot.

Der Fehler war nicht die Zahl, sondern die Kopie. Ein Gate, das verlangt, dass
ein handgepflegtes Literal einem automatischen Bump folgt, hat seinen
Fehlschlag im Normalbetrieb: Dependabot rührt diese Datei nicht an, also ist
jeder Routine-Bump ein roter Standard-Branch. Ein Gate, das bei jedem
gewöhnlichen Vorgang anspringt, wird abgeschaltet — und dann fehlt es dort,
wo es nötig wäre.

`scripts/check_version_sync.py` hat die Regel längst formuliert, nur für
`src/`: «ein wieder eingefügtes Literal wäre der Beginn derselben Drift». Für
diese Datei gilt sie genauso. Der Test heisst deshalb jetzt umgekehrt — er
prüft, dass hier **keine** Version wiederholt wird.

Vor dem Lauf `ruff --version` prüfen: ein älteres ruff früher im `PATH`
schlägt den Pin, ohne dass der Install etwas meldet.

**Gates, wörtlich aus der CI:**

```bash
python scripts/check_ruff_pin.py
ruff check src/ tests/ scripts/
ruff format --check src/ tests/ scripts/
python -m py_compile src/srgssr_mcp/server.py
python scripts/check_version_sync.py
python scripts/check_dependabot_labels.py
pytest -m "not live" --cov=src --cov-report=term-missing --cov-fail-under=80
```

**«Die CI» sind hier zwei Workflows.** Die ersten sechs Befehle stehen im Job
`quality` in `ci.yml`, der `pytest` allein im Job `test` in `test.yml` —
beide mit Matrix 3.11/3.12/3.13, beide auf `push`/`pull_request` gegen `main`.
Ein roter Check «CI» und ein roter Check «Tests» zeigen also auf verschiedene
Dateien; wer nach dem falschen sucht, findet nichts. In `test.yml` trägt der
`pytest` zusätzlich `--cov-report=xml` für den Upload danach — der Upload ist
auf 3.11 beschränkt und `continue-on-error: true`, also kein Gate. Das
Coverage-Minimum von 80 % ist eines: es steht im `pytest`-Aufruf selbst.

**Das Label-Gate steht, deklariert wird trotzdem nichts.**
`check_dependabot_labels.py` vergleicht, was `.github/dependabot.yml` unter
`labels:` verlangt, mit den Labels, die das Repo wirklich hat. Für einen
*deklarierten* Namen legt Dependabot nichts an, sondern kommentiert nur an
jedem PR und lässt ihn ungelabelt — kein roter Check, kein Log. Genau so ist es
hier gelaufen, die Meldung steht unter PR #48 vom 30.7.2026 und blieb einen
Monat liegen. In der CI kommt der Token aus `secrets.GITHUB_TOKEN`; fehlt er
dort, **fällt** der Schritt, statt zu überspringen — ein Gate, das ohne
Zugangsdaten durchwinkt, wäre die Attrappe, gegen die es gebaut ist. Lokal ohne
Token prüft es nur die Deklaration und sagt das ausdrücklich, ist also kein
Beleg.

**Die Deklaration selbst war der Fehler, nicht ihre Lücke.** PR #103 trug
`labels: ["dependencies"]` wieder ein und liess `github-actions` bewusst weg,
weil dieses Label hier gemessen nicht existiert (29.8.2026, 12:38 UTC:
`dependencies` als Treffer, `github-actions` als echtes «not found», mit
Positivkontrolle im selben Aufruf — die Methode dazu steht unter «Ein 403 ist
gar keine Auskunft» in Teil 1). Die Messung stimmt; der Schluss daraus nicht.
Das Ökosystem-Label fehlte, **weil** eine eigene Liste den Vorgabesatz ersetzt,
den Dependabot sonst selbst anlegt und pflegt. Die Abwesenheit war also die
Folge der Deklaration und nicht ihr Grund — dieselbe Umkehrung wie in Teil 1,
nur eine Ebene tiefer.

Seit diesem PR steht `labels:` deshalb in keinem der beiden Blöcke, und der
Ankertest sichert das zu. Ehrlicherweise heisst das: **das Gate prüft im
Moment nichts** — ohne Deklaration hat es keinen Namen abzugleichen. Es
bleibt trotzdem, weil es genau den Fall abfängt, der es nötig macht: sobald
jemand wieder eine Liste einträgt, wird ein fehlender Name dort ein roter
Check statt eines übersehenen Kommentars.

**`secret-scan.yml` gatet ebenfalls jeden PR** (gitleaks, gegen `main`) und
steht in keiner Liste — lokal stellt ihn keiner der Befehle oben nach. Ein
roter PR bei grünen Tests ist meistens er.

**Die Branch Protection steht seit dem 18.9.2026.** Gemessen am Head von
PR #121, gesetzt und zurückgelesen (`enforce_admins`, keine Review-Pflicht),
acht Kontexte:

```
Gitleaks
quality (3.11)   quality (3.12)   quality (3.13)
test (3.11)      test (3.12)      test (3.13)
review-abgeschlossen   ← zu entfernen, der Workflow ist weg
```

**Der letzte Kontext hängt in der Luft.** Mit `codex-gate.yml` ist weg, was
ihn berichtet; ein required Kontext ohne Berichterstatter hält jeden PR auf.
Er muss von Hand aus der Branch Protection — eine Repo-Einstellung, die der
Agent-Proxy mit HTTP 403 sperrt.

**Achtung beim Suchen:** Der Kontext heisst `review-abgeschlossen`, nicht
`codex-gate`. Der Job trug keinen `name:`, also nahm GitHub die Job-ID. Wer
in den Einstellungen nach «codex» sucht, findet ihn nicht.

Dass die Liste gemessen und nicht abgeschrieben ist, ist hier keine Pedanterie:
Die Branch Protection war am Vormittag von Hand gesetzt worden, `codex-gate.yml`
entstand erst um 04:11 UTC desselben Tages. Eine von Hand gesetzte Liste kennt
keinen Kontext, den es beim Setzen noch nicht gab — `review-abgeschlossen` kam
deshalb erst im portfolioweiten Durchlauf am Abend dazu.

Wer hier einen Job umbenennt oder einen neuen Workflow auf `pull_request`
legt, muss die Liste nachziehen: ein umbenannter Check fällt still aus der
Anforderung, ein neuer kommt nicht von selbst hinein. Beides ist an einem PR
nicht zu sehen — die Checkliste sieht in beiden Fällen gesund aus.

Kein `include` unter `[tool.ruff]` setzen. Es stand dort auf
`["src/**/*.py"]` und hob die Pfadangabe der beiden ruff-Gates still wieder
auf: sie liefen grün, während sie nur `src/` prüften (behoben in #68).

**Fixtures: 25 Aufzeichnungen, und dieser Absatz hat sie einen Monat lang
geleugnet.** Hier stand bis zum 20.9.2026 «der Recorder steht, die
Aufzeichnungen fehlen noch» — während `tests/fixtures/` seit dem 16.8.2026
25 Antworten samt `PROVENANCE.md` trägt (Commit `3f54c90`) und
`tests/test_recorded_fixtures.py` sie mit 25 Tests abspielt, über **alle 15**
Werkzeuge. Die Portfolio-Konvention ist hier also erfüllt und war es beim
Lesen dieses Satzes schon.

Der Weg dahin gehört in die Akte, weil er zweimal an derselben Stelle
abgebogen ist. Die Messung vom 15.08.2026 stimmt — ohne Consumer Key
antworten Token-Endpunkt und alle fünf Produkt-Basen mit 401 —, aber die
Schlussfolgerung «also gibt es hier keine Fixtures» ging zu weit.
Nachgemessen am 16.08.2026: die 401 kommt von SRG SSR selbst (eigene Header,
CONNECT geht durch), der Host ist also erreichbar und es fehlen allein die
Credentials. Die liegen längst da, wo der nächtliche Live-Lauf sie nimmt.
`.github/workflows/record-fixtures.yml` fährt `scripts/record_fixtures.py` mit
denselben Secrets, auf Knopfdruck — und hat sie am selben Tag gefahren.

**Der zweite Fehler ist der lehrreichere.** Der erste war eine zu weite
Schlussfolgerung; der zweite war, sie nach ihrer Widerlegung stehen zu lassen.
Die Aufzeichnungen kamen, die Zeile blieb. Ein Satz, der einmal gemessen war,
altert nicht von selbst — und er altert still, weil kein Test ihn hält:
`check_version_sync.py` bewacht eine Zahl, aber niemand bewacht eine
Zustandsbehauptung über das Dateisystem. Aufgefallen ist es beim
Release-Vorlauf zu 2.1.0, als jemand die Werkzeuge zählte und dabei über den
Ordner stolperte.

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

Aufzeichnungen und Live-Lauf beantworten verschiedene Fragen, und keiner
ersetzt den anderen: Die Fixtures halten die Drahtform von gestern fest und
laufen ohne Credentials, der nächtliche Live-Lauf prüft die Quelle von heute —
aber nur solange er *jedes* Werkzeug erreicht. Genau das hält
`test_live_coverage.py` fest, samt der Probe im Docstring; die Abspielsuite
zählt ihrerseits gegen dieselbe Werkzeugliste.

**Live-Tests:** `.github/workflows/live-test.yml` läuft nächtlich per Cron
(`0 4 * * *`) plus `workflow_dispatch`, mit Credential-Guard vor dem Lauf; ein
roter Lauf öffnet ein Issue, der von Hand gestartete ebenso. Sie sind hier also
nicht bloss per `-m "not live"` ausgeschlossen. Der Workflow allein erfüllt
DRIFT-005 aber nicht — dazu gehört, Kadenz und Empfänger zu dokumentieren, und
das steht in `CONTRIBUTING.md`, gegen den Workflow gehalten von
`test_live_workflow_docs.py`.

**Der Cron sagt, worum er bittet — nicht, wann gelaufen wird.** Gemessen am
18.9.2026: Die vier vorangehenden `schedule`-Läufe wurden um 09:44, 09:18,
09:12 und 09:20 UTC erzeugt (14.–17.9.), also rund fünf Stunden nach der
deklarierten Zeit, und zwar jeder. Die naheliegende Ursache — GitHub verzögert
geplante Workflows unter Last — ist **nicht** gemessen; belegt sind die vier
Zeitstempel.

Hier stehen sie als Datum und nicht als gepflegter Wert: Eine Zeile «läuft
effektiv um 09:20» wäre die nächste Kopie, die driftet, und zwar gegen etwas,
das niemand steuert. Vier datierte Beobachtungen veralten nicht, sie werden
Geschichte.

`test_live_workflow_docs.py` fällt deshalb hier nicht ein — und das ist kein
Mangel des Tests, sondern seine Grenze: Er hält `0 4 * * *` gegen «04:00 UTC»
in beiden `CONTRIBUTING`-Dateien, also Deklaration gegen Deklaration. Die
tatsächliche Auslösezeit liegt bei GitHub und in keiner Datei dieses Repos.
Was daraus folgt, steht in beiden `CONTRIBUTING`-Dateien: aus dem Cron nicht
schliessen, dass der Lauf stattgefunden hat — die Lauf-Liste fragen.
