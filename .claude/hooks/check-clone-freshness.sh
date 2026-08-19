#!/usr/bin/env bash
# SessionStart-Hook: meldet beim Sessionstart, wie viele Commits der
# ausgecheckte Stand hinter origin/<default-branch> liegt.
#
# GRUND: Ein veralteter Klon hat am 3.8.2026 zweimal eine rote CI erzeugt,
# deren Ursache nicht im Diff stand — die fehlenden Commits waren jeweils
# genau die, die das Gate einfuehrten, an dem der Branch scheiterte. Die
# Pruefung kostet eine Sekunde und ersetzt eine Fehlersuche in den falschen
# Dateien.
#
# OBERSTE REGEL: Dieser Hook blockiert die Session nie. Kein Netz, kein
# Remote, detached HEAD, flatterndes DNS, fehlendes git — jeder dieser Faelle
# geht still durch. Ein Hook, der bei Netzproblemen die Arbeit anhaelt, wird
# nach dem zweiten Mal abgeschaltet und schuetzt danach gar nichts. Deshalb:
#   * kein `set -e` (ein fehlgeschlagenes git soll weiterlaufen, nicht abbrechen),
#   * jeder Ausstieg ist `exit 0`,
#   * `trap ... EXIT` faengt auch einen Absturz ab, an den hier niemand dachte.
#
# ZWEITE REGEL: Der Default-Branch wird ermittelt, nicht als "main"
# angenommen. Drei Server im Portfolio (openlex-mcp, swiss-courts-mcp,
# swisstopo-mcp) heissen ihn `master`; ein fest verdrahtetes origin/main
# scheitert dort mit «couldn't find remote ref main» — was wie ein
# Netzproblem aussieht und den veralteten Klon genau so stehen laesst.
# Diese Annahme hat schon einmal einen Branch 15 Commits alt werden lassen.

set -u
trap 'exit 0' EXIT

# Sekunden, die das fetch hoechstens dauern darf. Bewusst klein: der
# Sessionstart darf nicht am Netz haengen.
readonly ZEITLIMIT=6

# Kein Passwort-Prompt, keine SSH-Rueckfrage: beides wuerde bis zum Timeout
# blockieren, statt zu scheitern.
export GIT_TERMINAL_PROMPT=0
export GIT_ASKPASS=true
export SSH_ASKPASS=true
export GIT_SSH_COMMAND="${GIT_SSH_COMMAND:-ssh -o BatchMode=yes -o ConnectTimeout=5}"

# `timeout` deckt jeden Transport ab (auch haengendes SSH). Fehlt es, tragen
# die http.lowSpeed*-Optionen unten den http-Fall allein.
mit_zeitlimit() {
  if command -v timeout >/dev/null 2>&1; then
    timeout "${ZEITLIMIT}s" "$@"
  else
    "$@"
  fi
}

git_zaehmt() {
  mit_zeitlimit git -c http.lowSpeedLimit=1000 -c "http.lowSpeedTime=${ZEITLIMIT}" "$@"
}

cd "${CLAUDE_PROJECT_DIR:-.}" 2>/dev/null || exit 0

# Deckt beides ab: kein Repo — und kein git im PATH. Ein zusaetzliches
# `command -v git` stand hier, bis eine Gegenprobe zeigte, dass sein
# Entfernen keinen einzigen Test kippt: bash schreibt sein «command not
# found» in genau dieses `2>&1`, der Rueckgabewert 127 laeuft in dasselbe
# `|| exit 0`. Eine Zusicherung, die keine Probe verteidigt, ist keine.
git rev-parse --git-dir >/dev/null 2>&1 || exit 0
git remote get-url origin >/dev/null 2>&1 || exit 0
# Leeres Repo ohne einen einzigen Commit: nichts zu vergleichen.
git rev-parse --verify --quiet HEAD >/dev/null 2>&1 || exit 0

# Default-Branch beim Remote erfragen — nicht raten. `head -n1`, weil
# ls-remote mehr als eine Zeile liefern kann.
default_branch=$(
  git_zaehmt ls-remote --symref origin HEAD 2>/dev/null \
    | sed -n 's|^ref: refs/heads/\([^[:space:]]*\).*|\1|p' \
    | head -n1
)

# Fallback fuer den Fall, dass der Remote nicht antwortet: der lokal
# gecachte origin/HEAD. Sagt nur, was beim letzten Klon galt — reicht aber,
# um den richtigen Branch zu benennen.
if [ -z "$default_branch" ]; then
  default_branch=$(
    git symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null \
      | sed 's|^origin/||'
  )
fi
# Keine Zusicherung, sondern eine gesparte Netzrunde: bleibt der Name leer,
# waere das fetch unten `refs/heads/` und scheiterte ohnehin. Eine Gegenprobe
# zeigt das — ihr Entfernen kippt keinen Test. Die Zeile steht hier, damit
# der Hook in diesem Fall gar nicht erst ins Netz greift.
[ -n "$default_branch" ] || exit 0

# Voller Refspec statt blossem Branchnamen: so ist FETCH_HEAD eindeutig
# dieser eine Ref. Scheitert das fetch (kein Netz, Timeout, Ref weg), wird
# geschwiegen — eine Zahl aus einem veralteten Cache waere schlechter als
# keine Zahl.
git_zaehmt fetch --quiet origin "refs/heads/${default_branch}" >/dev/null 2>&1 || exit 0

rueckstand=$(git rev-list --count HEAD..FETCH_HEAD 2>/dev/null) || exit 0
case "$rueckstand" in
  ''|*[!0-9]*) exit 0 ;;   # keine Zahl -> nichts behaupten
  0) exit 0 ;;             # aktuell -> schweigen
esac

if [ "$rueckstand" = "1" ]; then
  commits="1 Commit"
else
  commits="${rueckstand} Commits"
fi

cat <<MELDUNG
[Klon-Aktualitaet] Der ausgecheckte Stand liegt ${commits} hinter origin/${default_branch}.

    git pull origin ${default_branch}

Grund: Ein veralteter Klon hat am 3.8.2026 zweimal eine rote CI erzeugt, deren
Ursache nicht im Diff stand — die fehlenden Commits waren jeweils genau die,
die das Gate einfuehrten, an dem der Branch scheiterte. Die Pruefung kostet
eine Sekunde und ersetzt eine Fehlersuche in den falschen Dateien.
MELDUNG

exit 0
