"""Das Gate um `scripts/check_dependabot_labels.py`.

Der Check ist nur so viel wert wie die Frage, ob er auch faellt. Jeder Test hier
zielt auf eine andere Art, ihn wirkungslos zu machen:

  - die Extraktion greift zu weit (Nachbarschluessel als Label),
  - sie greift zu kurz (Inline-Form, zweite Seite der API),
  - der Vergleich meldet nichts,
  - der Lauf wird ohne Token still gruen.

Die letzte ist die gefaehrlichste: ein Gate, das ohne Zugangsdaten durchwinkt,
ist genau die Attrappe, gegen die es gebaut wurde.
"""

from __future__ import annotations

import importlib.util
import pathlib

import pytest

_ROOT = pathlib.Path(__file__).resolve().parents[1]


def _skript():
    """Laedt das Skript ueber den Dateipfad — `scripts/` ist kein Paket.

    Bewusst dasselbe Modul, das die CI aufruft: eine nachgebaute Kopie der
    Extraktion koennte sich davon fortbewegen, ohne dass es auffaellt.
    """
    pfad = _ROOT / "scripts" / "check_dependabot_labels.py"
    spec = importlib.util.spec_from_file_location("check_dependabot_labels", pfad)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


@pytest.fixture(scope="module")
def skript():
    return _skript()


BLOCK = """\
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "monthly"
    labels:
      - "dependencies"
      - "ci"
"""

INLINE = """\
version: 2
updates:
  - package-ecosystem: "pip"
    labels: ["dependencies", "python"]
"""

OHNE = """\
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
"""

# Zwei Eintraege, wobei der zweite direkt auf den `labels:`-Block des ersten
# folgt. Das ist die Anordnung, an der eine Extraktion ohne Einrueckungspruefung
# scheitert: sie liest ueber die Blockgrenze hinaus weiter und nimmt
# `- package-ecosystem: "github-actions"` als Label auf.
ZWEI_EINTRAEGE = """\
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/"
    labels:
      - "dependencies"

  - package-ecosystem: "github-actions"
    directory: "/"
    labels:
      - "ci"
"""


def test_die_block_form_wird_gelesen(skript) -> None:
    assert skript.declared_labels(BLOCK) == {"dependencies", "ci"}


def test_die_inline_form_wird_gelesen(skript) -> None:
    """`labels: ["a", "b"]` ist gueltiges YAML und kommt im Portfolio vor.

    Wer nur die Block-Form liest, meldet fuer diese Repos «keine Labels
    verlangt» — und das Gate winkt sie durch.
    """
    assert skript.declared_labels(INLINE) == {"dependencies", "python"}


def test_nachbarschluessel_sind_keine_labels(skript) -> None:
    """Der Fehler, der beim ersten Anlauf tatsaechlich passiert ist.

    Ein Griff nach allen Zeichenketten in der Naehe von `labels:` faengt
    `directory: "/"` und `interval: "monthly"` mit ein und meldet `/` als
    fehlendes Label. Das Gate waere dann dauerhaft rot, ohne dass etwas fehlt —
    und wuerde abgeschaltet.
    """
    gefunden = skript.declared_labels(BLOCK)
    assert "/" not in gefunden
    assert "monthly" not in gefunden


def test_der_labels_block_endet_am_naechsten_eintrag(skript) -> None:
    """Die schaerfere Haelfte derselben Falle.

    Folgt auf den `labels:`-Block direkt der naechste Update-Eintrag, muss die
    Extraktion an der Einrueckung abbrechen. Ohne diese Pruefung liest sie
    weiter und meldet `package-ecosystem: "github-actions"` als Label — ein
    Label, das nie existieren kann, also ein dauerhaft rotes Gate.
    """
    gefunden = skript.declared_labels(ZWEI_EINTRAEGE)
    assert gefunden == {"dependencies", "ci"}
    assert not any("package-ecosystem" in eintrag for eintrag in gefunden)


def test_ohne_labels_block_wird_nichts_verlangt(skript) -> None:
    assert skript.declared_labels(OHNE) == set()


def test_die_eigene_konfiguration_deklariert_keine_labels(skript) -> None:
    """Verankert den Parser an der echten Datei, nicht nur an Attrappen.

    Handgeschriebene Beispiele kodieren die Annahme des Autors — und diese
    Zusicherung hat genau das einmal getan: sie verlangte `dependencies` und
    machte damit die Annahme unwiderlegbar, die sie pruefen sollte.

    Die Optionsreferenz sagt es andersherum. Ohne `labels:` vergibt Dependabot
    `dependencies` und, weil hier zwei Paketmanager deklariert sind, ein
    Oekosystem-Label dazu — und legt beide selbst an. Eine eigene Liste
    ERSETZT diesen Satz und laesst unbekannte Namen stillschweigend fallen.
    Die Deklaration war deshalb kein Gewinn, sondern ein Tausch: ein sich
    selbst pflegender Vorgabesatz gegen eine starre Liste.
    """
    text = (_ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")
    gefunden = skript.declared_labels(text)
    assert gefunden == set(), (
        f"dependabot.yml deklariert {sorted(gefunden)}, erwartet ist keine "
        "Deklaration. Wer wieder eine Liste eintraegt, ersetzt damit den "
        "Vorgabesatz, den Dependabot sonst selbst anlegt und pflegt."
    )


def test_ein_fehlendes_label_macht_den_lauf_rot(skript, monkeypatch, capsys) -> None:
    monkeypatch.setenv("GH_TOKEN", "x")
    monkeypatch.setenv("GITHUB_REPOSITORY", "malkreide/srgssr-mcp")
    monkeypatch.setattr(skript, "config_text", lambda: BLOCK)
    monkeypatch.setattr(skript, "existing_labels", lambda slug, token: {"dependencies"})

    assert skript.main() == 1
    fehler = capsys.readouterr().err
    assert "ci" in fehler
    assert "gh label create ci" in fehler


def test_vollstaendige_labels_machen_den_lauf_gruen(skript, monkeypatch) -> None:
    monkeypatch.setenv("GH_TOKEN", "x")
    monkeypatch.setenv("GITHUB_REPOSITORY", "malkreide/srgssr-mcp")
    monkeypatch.setattr(skript, "config_text", lambda: BLOCK)
    monkeypatch.setattr(skript, "existing_labels", lambda slug, token: {"dependencies", "ci", "bug"})

    assert skript.main() == 0


def test_ohne_token_ist_der_lauf_in_der_ci_rot(skript, monkeypatch, capsys) -> None:
    """Die wichtigste Zusicherung: kein stilles Gruen ohne Zugangsdaten.

    Faellt der Token im Workflow weg — umbenanntes Secret, vergessener `env:`-
    Block —, dann pruefte das Gate nichts mehr. Ein Ueberspringen saehe in der
    CI-Ausgabe genauso aus wie ein Erfolg.
    """
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setenv("CI", "true")
    monkeypatch.setattr(skript, "config_text", lambda: BLOCK)

    assert skript.main() == 1
    assert "GH_TOKEN" in capsys.readouterr().err


def test_ohne_token_blockiert_er_lokal_nicht(skript, monkeypatch, capsys) -> None:
    """Lokal soll er niemanden aufhalten — aber sagen, dass er nur halb geprueft hat."""
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setattr(skript, "config_text", lambda: BLOCK)

    assert skript.main() == 0
    assert "nur die Deklaration" in capsys.readouterr().out


def test_ohne_dependabot_konfiguration_ist_nichts_zu_pruefen(skript, monkeypatch) -> None:
    monkeypatch.setattr(skript, "config_text", lambda: None)
    assert skript.main() == 0


def test_die_zweite_seite_der_labels_wird_geholt(skript, monkeypatch) -> None:
    """Ohne Blaettern faende ein Repo mit ueber 100 Labels die spaeteren nicht.

    Das Gate waere dann falsch rot — die schlimmere Richtung waere ein
    Abbruch nach Seite 1 bei genau 100 Treffern, deshalb liefert die Attrappe
    hier volle 100 auf Seite 1.
    """
    seiten = {
        1: [{"name": f"l{i}"} for i in range(100)],
        2: [{"name": "dependencies"}],
        3: [],
    }
    geholt: list[int] = []

    class _Antwort:
        def __init__(self, nutzlast):
            self._nutzlast = nutzlast

        def read(self):
            import json

            return json.dumps(self._nutzlast).encode()

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    gesehen: list[object] = []

    def _urlopen(request, timeout=None):
        import urllib.parse

        gesehen.append(request)
        seite = int(urllib.parse.parse_qs(request.full_url.split("?", 1)[1])["page"][0])
        geholt.append(seite)
        return _Antwort(seiten[seite])

    monkeypatch.setattr(skript.urllib.request, "urlopen", _urlopen)
    namen = skript.existing_labels("malkreide/srgssr-mcp", "x")

    assert geholt == [1, 2]
    assert "dependencies" in namen
    assert len(namen) == 101


def test_die_anfrage_traegt_token_und_api_version(skript, monkeypatch) -> None:
    """Die Form der Anfrage, die lokal nicht live geprueft werden kann.

    In dieser Umgebung ist `api.github.com` gesperrt; der echte Aufruf laeuft
    erstmals in der CI. Eine falsch gebaute Anfrage — fehlender Token, falscher
    Pfad — endete dort in einem 401 oder 404, und der Check faellt dann mit
    «nicht abrufbar» statt mit einem Befund. Diese Zusicherung haelt die Form
    fest, damit das nicht erst in der CI auffaellt.
    """
    gesehen: list[object] = []

    class _Leer:
        def read(self):
            return b"[]"

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    def _urlopen(request, timeout=None):
        gesehen.append(request)
        return _Leer()

    monkeypatch.setattr(skript.urllib.request, "urlopen", _urlopen)
    skript.existing_labels("malkreide/srgssr-mcp", "geheim")

    anfrage = gesehen[0]
    assert anfrage.full_url.startswith("https://api.github.com/repos/malkreide/srgssr-mcp/labels?")
    assert "per_page=100" in anfrage.full_url
    # urllib normalisiert Header-Namen auf Kleinschreibung mit grossem Anfang.
    assert anfrage.get_header("Authorization") == "Bearer geheim"
    assert anfrage.get_header("Accept") == "application/vnd.github+json"
    assert anfrage.get_header("X-github-api-version") == "2022-11-28"
