"""Der SessionStart-Hook meldet einen veralteten Klon — und blockiert nie.

`.claude/hooks/check-clone-freshness.sh` existiert wegen des 3.8.2026: ein
veralteter Klon erzeugte zweimal eine rote CI, deren Ursache nicht im Diff
stand. Der Hook nimmt einem das Nachdenken daran ab, taugt dafür aber nur,
solange zwei Eigenschaften halten — und beide fallen still aus, wenn sie
brechen:

* **Er blockiert nicht.** Ein Hook, der bei Netzproblemen den Sessionstart
  anhält, wird nach dem zweiten Mal abgeschaltet und schützt danach gar
  nichts. Ein Regressionsfehler hier meldet sich nicht als Fehlermeldung,
  sondern als hängender Sessionstart, den niemand dem Hook zuordnet.
* **Er ermittelt den Default-Branch.** Drei Server im Portfolio nennen ihn
  `master`. Ein fest verdrahtetes `origin/main` scheitert dort — still, mit
  `exit 0`, weil Regel eins das so verlangt. Der Hook schwiege dann für immer
  und sähe dabei aus wie ein Hook, der nichts zu melden hat.

Deshalb prüft hier nichts den Skripttext, sondern jeder Test fährt das Skript
gegen echte Wegwerf-Repos: Default-Branch `master`, toter Remote, hängendes
`git`, detached HEAD, aktueller Stand. Ein Test gegen den Text hätte die
Annahme des Autors bloss wiederholt.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import textwrap
import time

import pytest

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_SETTINGS = _ROOT / ".claude" / "settings.json"
_HOOK = _ROOT / ".claude" / "hooks" / "check-clone-freshness.sh"

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git nicht verfügbar")


def _git(cwd: pathlib.Path, *args: str) -> str:
    """git im Wegwerf-Repo, abgeschirmt von der Konfiguration des Rechners."""
    umgebung = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@example.invalid",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.invalid",
    }
    fertig = subprocess.run(["git", *args], cwd=cwd, env=umgebung, capture_output=True, text=True, check=True)
    return fertig.stdout


def _hook(
    projekt: pathlib.Path,
    *,
    pfad_prefix: pathlib.Path | None = None,
    pfad: pathlib.Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """Den Hook so fahren, wie Claude Code ihn fährt: `CLAUDE_PROJECT_DIR` gesetzt."""
    umgebung = {**os.environ, "CLAUDE_PROJECT_DIR": str(projekt), "GIT_CONFIG_GLOBAL": os.devnull}
    if pfad_prefix is not None:
        umgebung["PATH"] = f"{pfad_prefix}{os.pathsep}{umgebung['PATH']}"
    if pfad is not None:
        umgebung["PATH"] = str(pfad)
    return subprocess.run(
        [str(_HOOK)],
        cwd=str(projekt),
        env=umgebung,
        capture_output=True,
        text=True,
        timeout=60,
    )


def _commit(repo: pathlib.Path, text: str) -> None:
    (repo / "datei.txt").write_text(text)
    _git(repo, "add", "datei.txt")
    _git(repo, "commit", "-m", text)


@pytest.fixture
def klon_hinter_master(tmp_path: pathlib.Path) -> pathlib.Path:
    """Ein Klon, der zwei Commits hinter einem Remote mit Default-Branch `master` liegt.

    Bewusst `master`, nicht `main`: das ist der Fall, den die Annahme
    «origin/main» verschluckt.
    """
    remote = tmp_path / "remote.git"
    remote.mkdir()
    _git(remote, "init", "--bare", "--quiet", ".")
    # Nicht `--initial-branch`: das gibt es erst ab git 2.28.
    _git(remote, "symbolic-ref", "HEAD", "refs/heads/master")

    quelle = tmp_path / "quelle"
    quelle.mkdir()
    _git(quelle, "init", "--quiet", ".")
    _git(quelle, "checkout", "--quiet", "-b", "master")
    _commit(quelle, "eins")
    _git(quelle, "remote", "add", "origin", str(remote))
    _git(quelle, "push", "--quiet", "origin", "master")

    klon = tmp_path / "klon"
    _git(tmp_path, "clone", "--quiet", str(remote), str(klon))

    _commit(quelle, "zwei")
    _commit(quelle, "drei")
    _git(quelle, "push", "--quiet", "origin", "master")
    return klon


def test_meldet_rueckstand_gegen_den_ermittelten_default_branch(klon_hinter_master: pathlib.Path) -> None:
    """Zwei Commits fehlen, der Default-Branch heisst `master` — beides steht in der Meldung."""
    ergebnis = _hook(klon_hinter_master)

    assert ergebnis.returncode == 0
    assert "2 Commits" in ergebnis.stdout
    assert "origin/master" in ergebnis.stdout
    # Der eigentliche Punkt: nirgends «main». Ein Hook mit fest verdrahtetem
    # origin/main scheitert hier still und liefe durch alle anderen Tests.
    assert "main" not in ergebnis.stdout


def test_nennt_den_grund_damit_die_meldung_nicht_weggeklickt_wird(klon_hinter_master: pathlib.Path) -> None:
    """Die Meldung trägt den Vorfall, sonst liest sie sich wie ein Hinweis ohne Kosten."""
    ergebnis = _hook(klon_hinter_master)

    assert "3.8.2026" in ergebnis.stdout
    assert "git pull origin master" in ergebnis.stdout


def test_schweigt_wenn_der_klon_aktuell_ist(tmp_path: pathlib.Path, klon_hinter_master: pathlib.Path) -> None:
    """Bei 0 fehlenden Commits keine Ausgabe — sonst wird die Meldung zur Tapete."""
    _git(klon_hinter_master, "pull", "--quiet", "origin", "master")

    ergebnis = _hook(klon_hinter_master)

    assert ergebnis.returncode == 0
    assert ergebnis.stdout == ""


def test_detached_head_blockiert_nicht(klon_hinter_master: pathlib.Path) -> None:
    """Ausgecheckter Commit statt Branch: geht durch, mit exit 0."""
    sha = _git(klon_hinter_master, "rev-parse", "HEAD").strip()
    _git(klon_hinter_master, "checkout", "--quiet", "--detach", sha)

    ergebnis = _hook(klon_hinter_master)

    assert ergebnis.returncode == 0


def test_unerreichbarer_remote_blockiert_nicht(klon_hinter_master: pathlib.Path) -> None:
    """Kein Netz, kein Remote-Verzeichnis mehr: still durch, ohne Fehlerausgabe."""
    _git(klon_hinter_master, "remote", "set-url", "origin", str(klon_hinter_master / "gibt-es-nicht.git"))

    ergebnis = _hook(klon_hinter_master)

    assert ergebnis.returncode == 0
    assert ergebnis.stdout == ""
    assert ergebnis.stderr == "", "git-Fehlermeldungen gehoeren nicht in den Sessionstart"


def test_haengendes_git_wird_nach_wenigen_sekunden_abgebrochen(
    tmp_path: pathlib.Path, klon_hinter_master: pathlib.Path
) -> None:
    """Flatterndes DNS als Ernstfall: `ls-remote`/`fetch` hängen, der Hook nicht.

    Ein `git`-Doppelgänger früher im PATH schläft bei genau diesen beiden
    Unterbefehlen 120 Sekunden und reicht alles andere ans echte git weiter.
    Ohne Zeitlimit im Hook liefe dieser Test in seinen eigenen 60-Sekunden-
    Timeout — die Zusicherung hängt also an echter Zeit, nicht an einer
    gestellten Uhr.
    """
    echtes_git = shutil.which("git")
    assert echtes_git is not None
    schummel = tmp_path / "bin"
    schummel.mkdir()
    (schummel / "git").write_text(
        textwrap.dedent(f"""\
        #!/usr/bin/env bash
        for arg in "$@"; do
          case "$arg" in
            ls-remote|fetch) sleep 120 ;;
          esac
        done
        exec {echtes_git} "$@"
        """)
    )
    (schummel / "git").chmod(0o755)

    start = time.monotonic()
    ergebnis = _hook(klon_hinter_master, pfad_prefix=schummel)
    gebraucht = time.monotonic() - start

    assert ergebnis.returncode == 0
    assert ergebnis.stdout == ""
    assert gebraucht < 30, f"Hook hing {gebraucht:.1f}s — das Zeitlimit auf dem fetch greift nicht"


def test_default_branch_faellt_auf_gecachtes_origin_head_zurueck(
    tmp_path: pathlib.Path, klon_hinter_master: pathlib.Path
) -> None:
    """`ls-remote` scheitert, `fetch` geht: der Branchname kommt aus dem Cache.

    Der schmale, aber echte Fall — eine Abfrage geht daneben, die nächste
    nicht. Ohne den Rückfall bliebe `default_branch` leer und der Hook
    schwiege, obwohl zwei Commits fehlen: also genau das stille Versagen, vor
    dem der ganze Hook schützen soll.
    """
    echtes_git = shutil.which("git")
    assert echtes_git is not None
    schummel = tmp_path / "bin-ohne-lsremote"
    schummel.mkdir()
    (schummel / "git").write_text(
        textwrap.dedent(f"""\
        #!/usr/bin/env bash
        for arg in "$@"; do
          [ "$arg" = ls-remote ] && exit 1
        done
        exec {echtes_git} "$@"
        """)
    )
    (schummel / "git").chmod(0o755)

    ergebnis = _hook(klon_hinter_master, pfad_prefix=schummel)

    assert ergebnis.returncode == 0
    assert "2 Commits" in ergebnis.stdout
    assert "origin/master" in ergebnis.stdout


def test_repo_ohne_remote_schweigt(tmp_path: pathlib.Path) -> None:
    """Kein `origin`: nichts zu vergleichen, also nichts zu sagen."""
    repo = tmp_path / "solo"
    repo.mkdir()
    _git(repo, "init", "--quiet", ".")
    _commit(repo, "eins")

    ergebnis = _hook(repo)

    assert ergebnis.returncode == 0
    assert ergebnis.stdout == ""
    assert ergebnis.stderr == ""


def test_repo_ohne_commit_schweigt(tmp_path: pathlib.Path) -> None:
    """Frisch initialisiert, HEAD zeigt ins Leere: kein Absturz."""
    repo = tmp_path / "leer"
    repo.mkdir()
    _git(repo, "init", "--quiet", ".")

    ergebnis = _hook(repo)

    assert ergebnis.returncode == 0
    assert ergebnis.stdout == ""
    assert ergebnis.stderr == ""


def test_verzeichnis_ohne_git_schweigt(tmp_path: pathlib.Path) -> None:
    """Kein Repo: der Hook läuft auch dort, ohne zu meckern."""
    ergebnis = _hook(tmp_path)

    assert ergebnis.returncode == 0
    assert ergebnis.stdout == ""
    assert ergebnis.stderr == "", "git-Fehlermeldungen gehoeren nicht in den Sessionstart"


def test_ohne_git_im_pfad_schweigt(tmp_path: pathlib.Path, klon_hinter_master: pathlib.Path) -> None:
    """Ein Repo, aber kein `git` erreichbar: still durch, ohne «command not found»."""
    # PATH mit allem, was das Skript sonst braucht — nur ohne git. Ein leerer
    # PATH taugte nicht: dann fände schon die Shebang-Zeile ihre Shell nicht,
    # und der Test prüfte den Testaufbau statt den Hook.
    ohne_git = tmp_path / "bin-ohne-git"
    ohne_git.mkdir()
    for werkzeug in ("bash", "sed", "head", "cat", "env"):
        pfad_zum_werkzeug = shutil.which(werkzeug)
        if pfad_zum_werkzeug is None:
            pytest.skip(f"{werkzeug} nicht verfügbar")
        (ohne_git / werkzeug).symlink_to(pfad_zum_werkzeug)
    assert shutil.which("git", path=str(ohne_git)) is None

    ergebnis = _hook(klon_hinter_master, pfad=ohne_git)

    assert ergebnis.returncode == 0
    assert ergebnis.stdout == ""
    assert ergebnis.stderr == ""


def test_unerwarteter_fehler_beendet_die_session_nicht(tmp_path: pathlib.Path) -> None:
    """Der `trap ... EXIT` ist die letzte Verteidigungslinie — und wird hier ausgelöst.

    In eine Kopie des Skripts wird früh ein Zugriff auf eine nicht gesetzte
    Variable eingebaut: unter `set -u` bricht bash sofort mit 1 ab. Genau der
    Fall, an den beim Schreiben niemand dachte. Ohne `trap` reichte diese 1 an
    Claude Code durch; mit ihm bleibt es bei 0.

    Die erste Fassung dieses Tests hängte den Absturz *unten* an — dort kommt
    das Skript nie an, weil jeder Pfad vorher mit `exit 0` endet. Sie blieb
    grün, als der `trap` versuchsweise entfernt wurde, und prüfte damit nichts.
    """
    absturz = 'echo "${GIBT_ES_NICHT_ABSICHTLICH}"\n'
    anker = "readonly ZEITLIMIT="
    quelle = _HOOK.read_text()
    assert anker in quelle, "Anker verschoben — der Absturz landet sonst im Nirgendwo"
    mutante = tmp_path / "mutante.sh"
    mutante.write_text(quelle.replace(anker, absturz + anker, 1))
    mutante.chmod(0o755)

    ergebnis = subprocess.run(
        [str(mutante)],
        cwd=str(tmp_path),
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path)},
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert ergebnis.returncode == 0


def test_hook_ist_in_settings_json_registriert_und_ausfuehrbar() -> None:
    """Ein Skript, das nirgends eingetragen ist, läuft nie — und fällt nie auf."""
    einstellungen = json.loads(_SETTINGS.read_text())
    eintraege = einstellungen["hooks"]["SessionStart"]
    befehle = [h["command"] for gruppe in eintraege for h in gruppe["hooks"]]

    assert any(_HOOK.name in befehl for befehl in befehle), befehle
    assert _HOOK.is_file()
    assert os.access(_HOOK, os.X_OK), "Hook ist nicht ausführbar — Claude Code startet ihn nicht"
