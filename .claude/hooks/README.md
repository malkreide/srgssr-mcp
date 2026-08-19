# SessionStart-Hook: Klon-Aktualität

`check-clone-freshness.sh` meldet beim Sessionstart, wie viele Commits der
ausgecheckte Stand hinter `origin/<default-branch>` liegt. Liegt er nicht
zurück, sagt er nichts.

Registriert ist er in [`../settings.json`](../settings.json) für die Quellen
`startup` und `resume`. Der Grund steht hier und nicht dort, weil
`settings.json` striktes JSON ist und keinen Kommentar trägt.

## Warum

Ein veralteter Klon hat am 3.8.2026 zweimal eine rote CI erzeugt, deren
Ursache nicht im Diff stand — die fehlenden Commits waren jeweils genau die,
die das Gate einführten, an dem der Branch scheiterte. Man sucht dann in den
Dateien, die man selbst geändert hat, und findet dort nichts, weil dort auch
nichts ist. Die Prüfung kostet eine Sekunde und ersetzt eine Fehlersuche in
den falschen Dateien.

Dieselbe Prüfung steht als Handgriff in [`../../CLAUDE.md`](../../CLAUDE.md).
Ein Handgriff, an den man denken muss, wird vergessen — genau an den Tagen,
an denen er nötig wäre. Der Hook denkt daran.

## Die zwei Regeln, an denen er hängt

**Er blockiert die Session nie.** Kein Netz, kein Remote, detached HEAD,
flatterndes DNS, leeres Repo, fehlendes `git` — jeder dieser Fälle geht still
durch. Deshalb kein `set -e`, jeder Ausstieg `exit 0`, dazu ein
`trap 'exit 0' EXIT` für den Absturz, an den niemand dachte. Ein Hook, der bei
Netzproblemen die Arbeit anhält, wird nach dem zweiten Mal abgeschaltet und
schützt danach gar nichts.

Das `fetch` trägt ein Zeitlimit von 6 Sekunden (`timeout`, plus
`http.lowSpeedLimit`/`http.lowSpeedTime`, falls `timeout` fehlt), und
`GIT_TERMINAL_PROMPT=0` samt `ssh -o BatchMode=yes` verhindert, dass eine
Passwortabfrage bis zum Timeout wartet, statt sofort zu scheitern.
`settings.json` setzt zusätzlich `"timeout": 15` als zweiten Riegel.

**Der Default-Branch wird ermittelt, nicht angenommen.** Er kommt aus
`git ls-remote --symref origin HEAD`; antwortet der Remote nicht, aus dem
lokal gecachten `origin/HEAD`. Kommt beides leer zurück, schweigt der Hook,
statt ein `fetch` ohne Refspec abzusetzen — das fände still den Remote-HEAD
und endete mit 0, also genau dem Blindflug, den der Hook verhindern soll.

Drei Server im Portfolio (`openlex-mcp`, `swiss-courts-mcp`, `swisstopo-mcp`)
nennen ihren Default-Branch `master`. Ein fest verdrahtetes `origin/main`
scheitert dort mit «couldn't find remote ref main», was wie ein Netzproblem
aussieht — und den veralteten Klon genau so stehen lässt. Diese Annahme hat
schon einmal einen Branch 15 Commits alt werden lassen.

## Selber prüfen

```bash
CLAUDE_PROJECT_DIR="$PWD" .claude/hooks/check-clone-freshness.sh; echo "exit=$?"
```

`tests/test_session_start_hook.py` fährt das Skript gegen echte Wegwerf-Repos
(`master` als Default-Branch, toter Remote, detached HEAD, aktueller Stand)
und prüft jedes Mal beides: die Ausgabe und den Exit-Code.

## Gegenprobe

Jede Zusicherung wurde einzeln neutralisiert, um zu sehen, ob überhaupt ein
Test dagegen hält. Zwei Runden waren nötig — die erste deckte auf, dass zwei
vermeintliche Prüfungen nichts prüften:

| Neutralisiert | Es fällt |
|---|---|
| Default-Branch hart auf `main` | `test_meldet_rueckstand_gegen_den_ermittelten_default_branch`, `test_nennt_den_grund…` |
| Schweigen bei 0 entfernt | `test_schweigt_wenn_der_klon_aktuell_ist` |
| `timeout` auf `ls-remote`/`fetch` entfernt | `test_haengendes_git_wird_nach_wenigen_sekunden_abgebrochen` (Lauf: 13 s → 61 s) |
| `trap 'exit 0' EXIT` entfernt | `test_unerwarteter_fehler_beendet_die_session_nicht` |
| `2>/dev/null` am Repo-Check entfernt | `test_verzeichnis_ohne_git_schweigt` |
| `\|\| exit 0` am `fetch` entfernt | `test_unerreichbarer_remote_blockiert_nicht` |
| Rückfall auf gecachtes `origin/HEAD` entfernt | `test_default_branch_faellt_auf_gecachtes_origin_head_zurueck` |
| Hook nicht ausführbar (`chmod -x`) | 12 von 13 Tests |

Zwei Befunde aus der ersten Runde, beide behoben:

* Der `trap`-Test hängte seinen Absturz **unten** ans Skript. Dort kommt es
  nie an — jeder Pfad endet vorher mit `exit 0`. Der Test blieb grün, als der
  `trap` entfernt wurde. Er löst den Absturz jetzt früh aus, über eine nicht
  gesetzte Variable unter `set -u`.
* Ein zusätzliches `command -v git` stand vor dem Repo-Check. Sein Entfernen
  kippte keinen Test: bash schreibt sein «command not found» in genau dasselbe
  `2>&1`, und 127 läuft in dasselbe `|| exit 0`. Es ist ersatzlos raus.

Eine Zeile ist bewusst geblieben, ohne dass eine Probe sie verteidigt:
`[ -n "$default_branch" ] || exit 0`. Sie sichert nichts zu — das `fetch`
darunter scheiterte ohnehin —, sie spart nur eine sinnlose Netzrunde. Das
steht so auch im Skript, damit niemand sie später für eine Prüfung hält.
