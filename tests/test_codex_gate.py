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

import json
import os
import pathlib
import re
import shutil
import subprocess
import time

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
    """Ein Draft ist nicht mergebar, es gibt also nichts zu halten.

    Die zweite Begruendung stand hier bis zum 18.9.2026 und war falsch: «auf
    einem Draft loest Codex nichts aus». Unter #117 kam elf Sekunden nach dem
    Eroeffnen des Drafts ein Kommentar des Bots. Der Guard bleibt, seine
    Begruendung ist halbiert — und die widerlegte Haelfte war der Grund, warum
    die erste Fassung des Gates die Meldung fuer harmlos hielt.
    """
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
# Das echte Skript, gegen aufgezeichnete Kommentare
# ---------------------------------------------------------------------------

_FIXTURES = pathlib.Path(__file__).resolve().parent / "codex_gate_fixtures"

# Ein `gh`, das statt der API eine Datei ausgibt — aber den `--jq`-Ausdruck des
# Workflows wirklich anwendet, statt ihn zu umgehen.
#
# Das ist der Unterschied zur ersten Fassung: die legte fertig gefilterte
# Kommentartexte hin und konnte deshalb nicht bemerken, dass der Filter fehlte.
# Ein Stub, der die Arbeit des Originals vorwegnimmt, prueft das Original nicht
# — dieselbe Falle wie der handgeschriebene `_StubCtx` in #113, nur eine Ebene
# hoeher. Die Aufzeichnungen sind deshalb jetzt die rohen JSON-Antworten von
# `repos/{owner}/{repo}/issues/{n}/comments`, samt `user.login`.
_GH_STUB = """#!/bin/sh
AUSDRUCK=''
while [ $# -gt 0 ]; do
  if [ "$1" = "--jq" ]; then shift; AUSDRUCK="$1"; fi
  shift
done
[ -n "$AUSDRUCK" ] || { echo "der Workflow ruft gh ohne --jq" >&2; exit 64; }
exec jq -r "$AUSDRUCK" "$CODEX_GATE_FIXTURE"
"""

_HEAD_116 = "0ee99ed1d8ffda9914c0ade8dd38d5d9a5bebb38"


def _skript() -> str:
    """Der `run`-Block aus dem Workflow, unveraendert.

    Der Punkt der ganzen Uebung: geprueft wird, was in der CI laeuft. Ein
    nachgebauter Parser waere aus derselben Annahme geschrieben wie das
    Original und koennte es nicht widerlegen.
    """
    daten = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
    return daten["jobs"]["review-abgeschlossen"]["steps"][0]["run"]


def _fahre(
    fixture: str,
    head: str,
    tmp_path: pathlib.Path,
    *,
    warte: str = "1",
) -> tuple[subprocess.CompletedProcess[str], float]:
    """Faehrt das echte Skript und gibt Ergebnis **und Dauer** zurueck.

    Die Dauer ist keine Zierde: an ihr haengt die Zusicherung, dass die
    Ausfalltexte erst nach Ablauf des Fensters zaehlen. Gemessen wird echte
    verstrichene Zeit gegen ein echtes `sleep` — eine gestellte Uhr, die nur
    beim Schlafen vorrueckt, koennte die Aussage nicht widerlegen.
    """
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
        "CODEX_GATE_FIXTURE": str(_FIXTURES / f"{fixture}.json"),
        "GH_TOKEN": "irrelevant-fuer-den-stub",
        "REPO": "malkreide/srgssr-mcp",
        "PR": "116",
        "HEAD_SHA": head,
        "WARTE_SEKUNDEN": warte,
        "ABSTAND": "1",
    }
    beginn = time.monotonic()
    lauf = subprocess.run(["bash", str(skript)], capture_output=True, text=True, env=umgebung, timeout=60)
    return lauf, time.monotonic() - beginn


def test_jq_steht_zur_verfuegung():
    """Positivkontrolle fuer den Stub.

    Ohne `jq` faellt jeder Fall unten mit demselben Fehler, und zwar mit einem,
    der wie ein Befund aussieht. Fehlt es, soll genau eine Zeile das sagen.
    """
    assert shutil.which("jq"), "ohne jq prueft der Stub den --jq-Ausdruck des Workflows nicht"


def test_ein_abgeschlossener_review_fuer_diesen_head_laesst_durch(tmp_path):
    ergebnis, _ = _fahre("completed", _HEAD_116, tmp_path)
    assert ergebnis.returncode == 0, ergebnis.stdout + ergebnis.stderr
    assert "abgeschlossen" in ergebnis.stdout


def test_ein_laufender_review_laesst_nicht_durch(tmp_path):
    """Die Zusicherung, um die es geht: `Running` ist kein Ergebnis.

    Genau hier sind sechs PRs gemergt worden — im Fenster zwischen «ready» und
    `Completed`.
    """
    ergebnis, _ = _fahre("running", _HEAD_116, tmp_path)
    assert ergebnis.returncode == 1, ergebnis.stdout + ergebnis.stderr


def test_ein_ergebnis_fuer_einen_anderen_head_laesst_nicht_durch(tmp_path):
    """Ohne diesen Abgleich waere das Gate eine Attrappe: nach einem Push
    stuende das alte `Completed` weiter da und oeffnete fuer Code, den niemand
    gesehen hat."""
    ergebnis, _ = _fahre("completed", "deadbee" + "f" * 33, tmp_path)
    assert ergebnis.returncode == 1, ergebnis.stdout + ergebnis.stderr
    assert "0ee99ed" in ergebnis.stdout


@pytest.mark.parametrize("fixture", ["kontingent", "environment"])
def test_ein_ausfall_bei_codex_haelt_das_repo_nicht_an(fixture: str, tmp_path):
    """Die bewusste Luecke, und warum sie da ist.

    Laeuft das Fenster ab, ohne dass ein Ergebnis fuer diesen Head da ist, und
    steht statt dessen einer der Ausfalltexte im Thread, dann laesst das Gate
    durch und sagt es. Darauf zu blockieren hielte das Repo wegen einer Stoerung
    an — und ein Gate, das im Normalbetrieb anspringt, wird abgeschaltet.
    """
    ergebnis, _ = _fahre(fixture, _HEAD_116, tmp_path)
    assert ergebnis.returncode == 0, ergebnis.stdout + ergebnis.stderr
    assert "UNGEPRUEFT" in ergebnis.stdout


def test_ein_ausfalltext_beendet_das_warten_nicht_vorzeitig(tmp_path):
    """**Die Zusicherung aus #117**, und der teuerste Fehler der ersten Fassung.

    Am 18.9.2026 um 04:12:00 UTC schrieb Codex «create an environment for this
    repo» unter den elf Sekunden alten Draft #117 — elf Minuten nachdem #116 im
    selben Repo einen vollstaendigen Review bekommen hatte. Ein Kommentar
    verschwindet nicht, wenn der PR auf ready geht.

    Die erste Fassung prueste die Ausfalltexte zu Beginn jeder Runde und
    beendete den Job sofort. An genau dem PR, der das Gate einfuehrt, haette es
    damit durchgelassen, ohne dem Review die Gelegenheit zu geben — und an jedem
    weiteren PR mit derselben Meldung im Thread ebenso.

    Gemessen wird deshalb die Zeit: mit der Meldung **und** einem laufenden
    Review im Thread muss der Job das Fenster abwarten. Wandern die Textpruefungen
    zurueck in die Schleife, faellt diese Zusicherung — und nur sie.
    """
    ergebnis, dauer = _fahre("draft_meldung_dann_laufender_review", _HEAD_116, tmp_path, warte="3")
    assert dauer >= 2.0, (
        f"der Job war nach {dauer:.2f}s durch — er hat auf die Meldung hin sofort "
        "aufgegeben, statt das Fenster abzuwarten"
    )
    # Danach ist das Fenster ergebnislos abgelaufen; dann gilt die Ausnahme.
    assert ergebnis.returncode == 0, ergebnis.stdout + ergebnis.stderr
    assert "UNGEPRUEFT" in ergebnis.stdout


def test_eine_alte_ausfallmeldung_verhindert_kein_durchlassen(tmp_path):
    """Gegenrichtung zum Test darueber, und der Grund, warum er nicht genuegt.

    Steht die Meldung im Thread und kommt der Review trotzdem, muss das Gate
    normal oeffnen — und zwar sofort, nicht nach Ablauf des Fensters. Ohne
    diese Kontrolle waere «immer das ganze Fenster abwarten» eine gueltige
    Loesung, die jeden PR fuenf Minuten kostete.
    """
    ergebnis, dauer = _fahre("draft_meldung_dann_abgeschlossen", _HEAD_116, tmp_path, warte="3")
    assert ergebnis.returncode == 0, ergebnis.stdout + ergebnis.stderr
    assert "abgeschlossen" in ergebnis.stdout
    assert dauer < 2.0, f"der Job wartete {dauer:.2f}s, obwohl das Ergebnis vorlag"


def test_ein_mensch_kann_das_gate_nicht_mit_einem_zitat_entwaffnen(tmp_path):
    """Die zweite Luecke der ersten Fassung: sie las jeden Kommentar.

    Wer einen der Ausfalltexte zitiert — in einem PR, der ueber sie schreibt,
    liegt das nahe —, oeffnete das Gate damit. Der `--jq`-Ausdruck des Workflows
    filtert deshalb auf `chatgpt-codex-connector[bot]`, und der Stub oben wendet
    genau diesen Ausdruck an, statt ihn vorwegzunehmen.
    """
    ergebnis, _ = _fahre("mensch_zitiert_ausfalltext", _HEAD_116, tmp_path)
    assert ergebnis.returncode == 1, ergebnis.stdout + ergebnis.stderr
    assert "UNGEPRUEFT" not in ergebnis.stdout


def test_die_aufzeichnungen_tragen_ihren_nachweis():
    """Ohne Herkunft und Datum ist eine Aufzeichnung ein plausibel aussehendes
    Artefakt, das seine eigene Annahme bestaetigt."""
    nachweis = (_FIXTURES / "PROVENANCE.md").read_text(encoding="utf-8")
    namen = sorted(d.name for d in _FIXTURES.glob("*.json"))
    assert namen, "keine Aufzeichnungen gefunden"
    for name in namen:
        assert name in nachweis, f"{name} steht nicht im Nachweis"
    # Die beiden Kommentar-IDs, an denen die Aufnahmen haengen.
    assert "5724943260" in nachweis, "die ID der Statustabelle fehlt"
    assert "5725034944" in nachweis, "die ID der Draft-Meldung aus #117 fehlt"


def test_die_aufzeichnungen_sind_echte_api_antworten():
    """Eine Aufzeichnung ohne `user.login` koennte den Autorenfilter nicht
    pruefen — und der Test darueber saehe trotzdem gruen aus, weil `jq` auf
    einem fehlenden Feld schlicht nichts liefert."""
    for datei in sorted(_FIXTURES.glob("*.json")):
        eintraege = json.loads(datei.read_text(encoding="utf-8"))
        assert eintraege, datei.name
        for eintrag in eintraege:
            assert eintrag["user"]["login"], datei.name
            assert eintrag["body"], datei.name
            assert eintrag["created_at"], datei.name
