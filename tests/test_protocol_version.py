"""ARCH-012: die beiden Spec-Revisionen, gegen die dieser Server geprueft ist.

`mcp` 2.x bedient ZWEI Protokoll-Aeren ueber denselben Server; die erste
Anfrage einer Verbindung entscheidet, welche gilt:

* die **Legacy-Aera** mit `initialize`-Handshake — was heutige Clients
  sprechen. Sie deckelt bei `LATEST_HANDSHAKE_VERSION`.
* die **Modern-Aera** mit Pro-Request-Envelope, die `LATEST_MODERN_VERSION`
  erreicht.

`PROTOCOL_VERSION` beschreibt die MODERNE Aera. Das war bisher nicht gesagt,
und die Zusicherung daneben zeigte auf `LATEST_PROTOCOL_VERSION` — ein Alias
auf genau diese Version. Derselbe Wert, aber der Name verschweigt, dass es eine
zweite Aera gibt, und die konnte damit frei wandern. Sie steht jetzt daneben.

**Der Wert der Konstante aendert sich nicht.** Er war richtig, nur
unvollstaendig beschrieben — anders als in `bag-epl-mcp` und `parlament-mcp`,
wo eine Konstante drei Revisionen hinterherhinkte und korrigiert werden musste.

Ohne gemessenen Teil: dieses Repo baut keine ASGI-App, durch die sich ein
`initialize` schicken liesse. Die Aushandlung steht in
`mcp/server/runner.py::_negotiate_initialize` und haengt an keinem Transport —
an neun Schwester-Servern gemessen, hier an den SDK-Konstanten gehalten. Das
ist die schwaechere Form, und sie steht hier benannt statt unausgesprochen.
"""

from __future__ import annotations

import pathlib
import re

from mcp.types.version import (
    LATEST_HANDSHAKE_VERSION,
    LATEST_MODERN_VERSION,
    LATEST_PROTOCOL_VERSION,
    SUPPORTED_PROTOCOL_VERSIONS,
)

from srgssr_mcp._app import PROTOCOL_VERSION

REPO = pathlib.Path(__file__).resolve().parents[1]

# Datei und Ueberschrift, unter der die Revisionen dokumentiert stehen.
README_SECTIONS = (("README.md", "## MCP Protocol Version"), ("README.de.md", "## MCP Protocol Version"))

# Die Obergrenze der Handshake-Aera. Sie steht hier und nicht im `src/`: der
# Server setzt sie nicht, das SDK bestimmt sie. Eine zweite Konstante im
# Auslieferungspfad waere eine zweite Wahrheit, die driften kann.
DOCUMENTED_HANDSHAKE_VERSION = "2025-11-25"


def test_der_pin_nennt_die_moderne_revision_des_installierten_sdk() -> None:
    """Wie bisher, nur gegen die benannte Konstante statt gegen den Alias.

    Faellt das hier, ist die Loesung nicht, den Wert blind nachzuziehen: erst
    das Spec-Changelog zwischen den beiden Revisionen lesen, das
    Serververhalten pruefen, dann Konstante, READMEs und `CHANGELOG.md` in
    einem Commit anheben.
    """
    assert PROTOCOL_VERSION == LATEST_MODERN_VERSION, (
        f"gepinnt {PROTOCOL_VERSION}, das SDK erreicht modern {LATEST_MODERN_VERSION}"
    )


def test_die_handshake_aera_steht_wo_die_readmes_sie_nennen() -> None:
    """Die Aera, die bestehende Clients sprechen — und die bisher niemand hielt.

    Ein Client, der ueber den `initialize`-Handshake nach der modernen Revision
    fragt, bekommt diese Obergrenze zurueck, nicht das, wonach er gefragt hat.
    """
    assert LATEST_HANDSHAKE_VERSION == DOCUMENTED_HANDSHAKE_VERSION, (
        f"das SDK deckelt den Handshake jetzt bei {LATEST_HANDSHAKE_VERSION}, "
        f"die READMEs sagen {DOCUMENTED_HANDSHAKE_VERSION}"
    )


def test_latest_protocol_version_ist_der_alias_auf_die_moderne_aera() -> None:
    """Die Falle, gegen die dieses Repo abgesichert wird, benannt.

    Die urspruengliche Zusicherung lautete `PIN == LATEST_PROTOCOL_VERSION` und
    las sich vollstaendig. Sie war es nicht, und man sieht es dem Namen nicht
    an. Faellt dieser Test, hat das SDK die Bedeutung des Alias geaendert —
    dann ist die Aufteilung oben neu zu bewerten, nicht nur eine Zahl.
    """
    assert LATEST_PROTOCOL_VERSION == LATEST_MODERN_VERSION
    assert LATEST_PROTOCOL_VERSION != LATEST_HANDSHAKE_VERSION


def test_die_beiden_aeren_sind_verschieden() -> None:
    """Sagt, wann die Aufteilung oben wieder verschwinden darf: legt das SDK
    die Aeren eines Tages zusammen, ist sie redundant und gehoert zurueckgebaut.
    """
    assert LATEST_MODERN_VERSION > LATEST_HANDSHAKE_VERSION


def test_die_pins_sind_datierte_revisionen_und_keine_beweglichen_ziele() -> None:
    """«latest» oder eine Spanne waeren keine Festlegung."""
    for value in (PROTOCOL_VERSION, DOCUMENTED_HANDSHAKE_VERSION):
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", value), value


def test_beide_readmes_nennen_beide_revisionen() -> None:
    """Ein Pin, den die Doku anders angibt, ist kein Pin.

    Jede Sprache einzeln geprueft: im Portfolio sind EN und DE desselben Repos
    schon dreimal auseinandergelaufen, weil nur eine Fassung nachgezogen wurde
    und niemand die andere daneben gelegt hat.
    """
    for name, anchor in README_SECTIONS:
        text = (REPO / name).read_text(encoding="utf-8")
        parts = text.split(anchor, 1)
        assert len(parts) > 1, f"{name} hat keinen Abschnitt «{anchor}»"
        body = parts[1][:2500]
        for value in (PROTOCOL_VERSION, DOCUMENTED_HANDSHAKE_VERSION):
            assert value in body, f"{name} nennt {value} nicht im Abschnitt «{anchor}»"


def test_die_mitgliedschaftspruefung_allein_wuerde_nicht_reichen() -> None:
    """Die Negativkontrolle fuer den Import-Schutz in `_app.py`.

    Er prueft `PROTOCOL_VERSION not in SUPPORTED_PROTOCOL_VERSIONS` und faengt
    damit den Wegfall einer Revision ab — eine Drift kann er strukturell nicht
    sehen: die Liste ist rueckwaertskompatibel und enthaelt heute noch
    `2024-11-05`. Faellt dieser Test, hat das SDK die alten Revisionen
    entfernt; dann ist der Schutz dort tatsaechlich hinreichend und dieser Test
    darf weg.
    """
    assert "2025-06-18" in SUPPORTED_PROTOCOL_VERSIONS


def test_die_liste_umfasst_beide_aeren() -> None:
    """Warum die Mitgliedschaftspruefung nicht nur zu grosszuegig, sondern
    mehrdeutig ist: `SUPPORTED_PROTOCOL_VERSIONS` mischt beide Aeren in einer
    flachen Liste. Aus einer Mitgliedschaft folgt also nicht einmal, in welcher
    Aera eine Revision bedient wird."""
    assert LATEST_HANDSHAKE_VERSION in SUPPORTED_PROTOCOL_VERSIONS
    assert LATEST_MODERN_VERSION in SUPPORTED_PROTOCOL_VERSIONS


def test_die_readmes_nennen_die_alte_revision_nicht_mehr() -> None:
    """Die deutsche Fassung stand drei Revisionen hinter der englischen."""
    for name, anchor in README_SECTIONS:
        section = (REPO / name).read_text(encoding="utf-8").split(anchor, 1)[1][:2500]
        assert "2025-06-18" not in section, f"{name} nennt weiterhin die alte Revision"


def test_keine_readme_beschreibt_diesen_server_als_fastmcp_server() -> None:
    """Ueber die ganze Datei geprueft, nicht nur ueber den Protokoll-Abschnitt.

    Genau so ist es aufgefallen: der Abschnitt war nachgezogen, waehrend der
    Projektbaum weiter «FastMCP server» als Kommentar trug und ein Absatz
    weiter unten `FastMCP` das `outputSchema` exponieren liess. `pyproject.toml`
    haelt seit der Migration fest, dass `fastmcp` fallengelassen wurde und
    `mcp.server.fastmcp` ersatzlos entfernt ist — vier Stellen behaupteten
    trotzdem das Gegenteil.

    Die deutsche Fassung darf das Wort weiterhin nennen, um genau das zu
    verneinen; deshalb zaehlt hier die Behauptung, nicht das Vorkommen.
    """
    for name, _ in README_SECTIONS:
        text = (REPO / name).read_text(encoding="utf-8")
        for claim in ("FastMCP server", "FastMCP-Server", "FastMCP exposes", "FastMCP exponiert"):
            assert claim not in text, f"{name} beschreibt den Server als «{claim}»"
