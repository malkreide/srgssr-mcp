"""Der Merge-Gate-Workflow und das, was CLAUDE.md ueber ihn behauptet.

`codex-gate.yml` haelt den Merge auf, bis der Codex-Review des aktuellen Heads
durch ist. Er ist die Antwort auf sechs gemessene Faelle, in denen zwischen
«ready for review» und Merge zwei bis zwoelf Sekunden lagen, waehrend der
Review vierzig bis fuenfundachtzig braucht — jedes Mal bei einem PR, der die
Regel dagegen vor Augen hatte.

**Was diese Datei nicht kann.** Ob der Workflow den Merge wirklich sperrt,
haengt an einem Required-Check-Eintrag in der Branch Protection. Der steht in
keiner Datei dieses Repos, ist ueber die API dieses Tests nicht lesbar und
kann hier deshalb nicht geprueft werden. Ein gruener Lauf hier heisst: der
Workflow ist da und sagt dasselbe wie die Doku — nicht: der Merge ist
gesperrt. Das ist die schwaechere Form, und sie steht hier benannt statt
unausgesprochen.

Geprueft wird deshalb das, was in zwei Dateien steht und auseinanderlaufen
kann. Verglichen, nicht nachgeschrieben: eine Zusicherung, die die erwarteten
Werte selbst enthielte, waere aus derselben Annahme geschrieben wie die
Dateien und koennte ihnen nicht widersprechen. Dasselbe Vorgehen wie in
`test_live_workflow_docs.py`.
"""

from __future__ import annotations

import os
import pathlib
import re
import subprocess

import pytest
import yaml

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_WORKFLOW = _ROOT / ".github" / "workflows" / "codex-gate.yml"
_CLAUDE_MD = _ROOT / "CLAUDE.md"


def _workflow() -> str:
    assert _WORKFLOW.exists(), f"{_WORKFLOW} fehlt — ohne ihn ist der Rest gegenstandslos"
    return _WORKFLOW.read_text(encoding="utf-8")


def _claude_md() -> str:
    return _CLAUDE_MD.read_text(encoding="utf-8")


def test_der_workflow_laeuft_auf_den_ereignissen_die_einen_merge_ermoeglichen():
    """`ready_for_review` ist der gemessene Ausloeser der Falle, `synchronize`
    der Fall danach: ein Push erzeugt einen neuen Head, und ein Required Check
    muss auf genau diesem Head liegen, sonst ist der PR gar nicht mergebar."""
    text = _workflow()
    typen = re.search(r"pull_request:\s*\n\s*types:\s*\[([^\]]+)\]", text)
    assert typen, "kein `pull_request`-Trigger mit `types` gefunden"
    gefunden = {t.strip() for t in typen.group(1).split(",")}
    assert {"ready_for_review", "synchronize"} <= gefunden, gefunden


def test_der_workflow_laeuft_nicht_auf_drafts():
    """Auf einem Draft loest Codex nichts aus; ein Gate darauf wartete auf ein
    Ergebnis, das per Konstruktion nie kommt, und liefe in sein Timeout. Ein
    Draft ist ohnehin nicht mergebar, es gibt also nichts zu halten."""
    assert "github.event.pull_request.draft" in _workflow()


def test_der_workflow_gleicht_den_geprueften_commit_gegen_den_head_ab():
    """Die Zusicherung, auf die es ankommt.

    Ohne diesen Abgleich wuerde ein `Completed` fuer einen frueheren Head das
    Gate oeffnen — also genau der Fall, gegen den es gebaut ist. Die
    Statustabelle nennt den Commit, den sie geprueft hat.
    """
    text = _workflow()
    assert "HEAD_SHA" in text
    assert "github.event.pull_request.head.sha" in text


@pytest.mark.parametrize(
    "muster",
    [
        r"reached your Codex usage limits",
        r"create an environment for this repo",
    ],
)
def test_die_ausfalltexte_des_gates_stehen_auch_in_claude_md(muster: str):
    """Die zwei Faelle, in denen das Gate durchlaesst statt zu blockieren.

    Sie bedeuten, dass Codex hier ueberhaupt nicht pruefen kann — darauf zu
    blockieren hielte das Repo wegen einer Stoerung an. Beide Texte sind in
    `CLAUDE.md` unter «Wenn Codex gar nicht erst hinsieht» woertlich
    festgehalten; sie stehen also in zwei Dateien und koennen auseinanderlaufen.

    Faellt das hier, hat jemand einen der Texte an einer Stelle geaendert.
    Dann ist die Frage nicht, welche Stelle man nachzieht, sondern welchen Text
    Codex heute wirklich schickt — und der wird gemessen, nicht geraten.
    """
    assert re.search(muster, _workflow()), f"das Gate kennt {muster!r} nicht (mehr)"
    assert re.search(muster, _claude_md()), f"CLAUDE.md kennt {muster!r} nicht (mehr)"


def test_claude_md_wiederholt_die_wartezeit_des_workflows_nicht():
    """Dieselbe Lehre wie beim ruff-Pin, eine Datei weiter.

    In #114 stand die ruff-Version in `CLAUDE.md` **und** in `pyproject.toml`;
    der naechste Dependabot-Bump machte `main` rot. Die Wartezeit des Gates ist
    derselbe Fall im Kleinen: eine Zahl, die an zwei Stellen steht, driftet.
    `CLAUDE.md` verweist deshalb auf den Workflow, statt den Wert zu nennen.

    Grenze, ausgesprochen: geprueft wird der konkrete Wert, nicht jede
    denkbare Umschreibung. «rund fuenf Minuten» faenge dieser Test nicht — der
    Absatz in `CLAUDE.md` sagt genau deshalb «der Workflow nennt seine
    Wartezeit selbst».
    """
    # `WARTE_SEKUNDEN=${WARTE_SEKUNDEN:-300}` — gesucht ist der Vorgabewert,
    # nicht die Uebersteuerung, die `_fahre` unten setzt.
    treffer = re.search(r"WARTE_SEKUNDEN=\$\{WARTE_SEKUNDEN:-(\d+)\}", _workflow())
    assert treffer, "der Workflow nennt keine Wartezeit — dann ist diese Zusicherung gegenstandslos"
    wert = treffer.group(1)

    assert not re.search(rf"\b{wert}\b", _claude_md()), (
        f"CLAUDE.md nennt die Wartezeit {wert} des Gates. Sie gehoert nur in den "
        "Workflow — eine Kopie hier driftet bei der naechsten Anpassung, ohne dass "
        "etwas rot wird. Auf den Workflow verweisen, nicht den Wert nennen."
    )


def test_claude_md_nennt_die_grenze_des_gates():
    """Der Absatz muss sagen, dass der Workflow allein nichts sperrt.

    Ohne den Required-Check-Eintrag in der Branch Protection ist er ein
    sichtbarer Hinweis — und ein sichtbarer Hinweis ist genau das, was hier
    sechsmal nicht gereicht hat. Wer das nicht mitliest, haelt das Problem fuer
    geloest, weil eine Datei dazugekommen ist.
    """
    text = _claude_md()
    assert "codex-gate.yml" in text
    assert "Branch Protection" in text


def test_die_falschen_abhilfen_stehen_nicht_mehr_als_empfehlung():
    """Negativkontrolle zur Korrektur in diesem PR.

    Zwei Fassungen lang empfahl `CLAUDE.md` «ein Required Check, den Codex
    setzt» und «Auto-Merge statt Sofort-Merge». Gemessen am 18.9.2026 setzt
    Codex keinen Check, und Auto-Merge wartet auf Checks statt auf Kommentare —
    unter #116 waren die Repo-Checks dreizehn Sekunden VOR dem Ready-Klick
    gruen, Auto-Merge haette also frueher gemergt.

    Beide Formulierungen duerfen im Text weiter vorkommen — sie werden dort
    ausdruecklich widerlegt. Was nicht wiederkommen darf, ist die alte
    Empfehlung in ihrer Satzform.
    """
    text = _claude_md()
    assert "ein Required Check, den Codex setzt" not in text
    assert "schlicht\nAuto-Merge statt Sofort-Merge" not in text
    # Positivkontrolle: die Widerlegung steht da, der Absatz ist also nicht
    # einfach geloescht worden.
    assert "den gibt es nicht" in text
    assert "das mergt früher" in text


# ---------------------------------------------------------------------------
# Das echte Skript, gegen aufgezeichnete Kommentartexte
# ---------------------------------------------------------------------------

_FIXTURES = pathlib.Path(__file__).resolve().parent / "codex_gate_fixtures"

# Ein `gh`, das statt der API eine Datei ausgibt. Der Workflow ruft
# `gh api --paginate .../comments --jq '.[] | .body'` — die Ausgabe ist also
# der reine Kommentartext, und genau den legt dieser Ersatz hin.
_GH_STUB = """#!/bin/sh
cat "$CODEX_GATE_FIXTURE"
"""


def _skript() -> str:
    """Der `run`-Block aus dem Workflow, unveraendert.

    Der Punkt der ganzen Uebung: geprueft wird, was in der CI laeuft. Ein
    nachgebauter Parser waere aus derselben Annahme geschrieben wie das
    Original und koennte es nicht widerlegen — dieselbe Falle wie der
    handgeschriebene `_StubCtx`, der vierzehn kaputte `ctx.info`-Aufrufe gruen
    hielt, bis sie ueber die Drahtform gemessen wurden.
    """
    daten = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
    return daten["jobs"]["review-abgeschlossen"]["steps"][0]["run"]


def _fahre(fixture: str, head: str, tmp_path: pathlib.Path) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(_GH_STUB, encoding="utf-8")
    gh.chmod(0o755)

    skript = tmp_path / "gate.sh"
    skript.write_text(_skript(), encoding="utf-8")

    umgebung = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "CODEX_GATE_FIXTURE": str(_FIXTURES / fixture),
        "GH_TOKEN": "irrelevant-fuer-den-stub",
        "REPO": "malkreide/srgssr-mcp",
        "PR": "116",
        "HEAD_SHA": head,
        # Kurz genug, dass ein Timeout im Test Sekunden kostet und nicht fuenf
        # Minuten — der Wert selbst ist nicht die Zusicherung.
        "WARTE_SEKUNDEN": "1",
        "ABSTAND": "1",
    }
    return subprocess.run(["bash", str(skript)], capture_output=True, text=True, env=umgebung, timeout=60)


def test_ein_abgeschlossener_review_fuer_diesen_head_laesst_durch(tmp_path):
    ergebnis = _fahre("completed.txt", "0ee99ed1d8ffda9914c0ade8dd38d5d9a5bebb38", tmp_path)
    assert ergebnis.returncode == 0, ergebnis.stdout + ergebnis.stderr
    assert "abgeschlossen" in ergebnis.stdout


def test_ein_laufender_review_laesst_nicht_durch(tmp_path):
    """Die Zusicherung, um die es geht: `Running` ist kein Ergebnis.

    Genau hier sind sechs PRs gemergt worden — im Fenster zwischen «ready» und
    `Completed`.
    """
    ergebnis = _fahre("running.txt", "0ee99ed1d8ffda9914c0ade8dd38d5d9a5bebb38", tmp_path)
    assert ergebnis.returncode == 1, ergebnis.stdout + ergebnis.stderr


def test_ein_ergebnis_fuer_einen_anderen_head_laesst_nicht_durch(tmp_path):
    """Ohne diesen Abgleich waere das Gate eine Attrappe: nach einem Push
    stuende das alte `Completed` weiter da und oeffnete fuer Code, den niemand
    gesehen hat."""
    ergebnis = _fahre("completed.txt", "deadbee" + "f" * 33, tmp_path)
    assert ergebnis.returncode == 1, ergebnis.stdout + ergebnis.stderr
    assert "0ee99ed" in ergebnis.stdout


@pytest.mark.parametrize("fixture", ["kontingent.txt", "environment.txt"])
def test_ein_ausfall_bei_codex_haelt_das_repo_nicht_an(fixture: str, tmp_path):
    """Die bewusste Luecke, und warum sie da ist.

    Erschoepftes Kontingent und fehlende Environment heissen, dass Codex hier
    gar nicht pruefen kann. Ein Gate, das darauf blockiert, haelt das Repo
    wegen einer Stoerung an — und ein Gate, das im Normalbetrieb anspringt,
    wird abgeschaltet (die Lehre aus dem ruff-Literal, das `main` rot machte).
    Der Lauf sagt dafuer ausdruecklich, dass der PR ungeprueft ist.
    """
    ergebnis = _fahre(fixture, "0ee99ed1d8ffda9914c0ade8dd38d5d9a5bebb38", tmp_path)
    assert ergebnis.returncode == 0, ergebnis.stdout + ergebnis.stderr
    assert "UNGEPRUEFT" in ergebnis.stdout


def test_die_aufzeichnungen_tragen_ihren_nachweis():
    """Ohne Herkunft und Datum ist eine Aufzeichnung ein plausibel aussehendes
    Artefakt, das seine eigene Annahme bestaetigt."""
    nachweis = (_FIXTURES / "PROVENANCE.md").read_text(encoding="utf-8")
    for name in ("running.txt", "completed.txt", "kontingent.txt", "environment.txt"):
        assert (_FIXTURES / name).exists(), name
        assert name in nachweis, f"{name} steht nicht im Nachweis"
    assert "5724943260" in nachweis, "die Kommentar-ID der Aufnahme fehlt"
