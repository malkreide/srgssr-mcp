"""Die Messreihe und die Zahlen, die aus ihr abgeleitet werden.

Warum es diese Datei gibt: Das Eintragen **einer** Tabellenzeile hat dreimal
hintereinander Codex-Befunde erzeugt — #126, #127, #128 —, und jedes Mal
dieselben drei Arten:

1. ein Zaehler, der stehenblieb («neun Laeufe» neben zehn Zeilen),
2. ein Einzelwert der Tabelle, der zusaetzlich in der Prosa stand (`204 s`),
3. eine Ableitung, die die Tabelle ueberholt hatte («der langsamste Lauf»).

Dagegen stand eine `grep`-Checkliste in `CLAUDE.md`. Sie hat ihren eigenen
Autor zweimal unterlaufen — einmal, weil er sie beim Eintragen von #126 nicht
fuhr, und einmal, weil sein `grep` ohne `-i` lief und «Zehn Laeufe» am
Satzanfang uebersah. Eine Pruefung, die nur ausfuehrt, wer daran denkt, ist
keine.

Die Zusicherungen hier sind deshalb die drei Befundarten, maschinell. Sie
lesen beide Dateien, weil die Zahlen in `docs/codex-messreihe.md` stehen und
die Schluesse daraus in `CLAUDE.md`.
"""

import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_MESSREIHE = _ROOT / "docs" / "codex-messreihe.md"
_CLAUDE_MD = _ROOT / "CLAUDE.md"

# Nur die Zahlwoerter, die im Text wirklich als Zaehler vorkommen. Bewusst
# keine Ziffern: «11 Laeufe» schreibt hier niemand, und eine Regex ueber
# Ziffern fienge die Jahreszahlen und PR-Nummern gleich mit.
_ZAHLWORT = {
    "drei": 3,
    "vier": 4,
    "fuenf": 5,
    "fünf": 5,
    "sechs": 6,
    "sieben": 7,
    "acht": 8,
    "neun": 9,
    "zehn": 10,
    "elf": 11,
    "zwoelf": 12,
    "zwölf": 12,
    "dreizehn": 13,
    "vierzehn": 14,
    "fuenfzehn": 15,
    "fünfzehn": 15,
}


def _messreihe() -> str:
    return _MESSREIHE.read_text(encoding="utf-8")


def _claude_md() -> str:
    return _CLAUDE_MD.read_text(encoding="utf-8")


def _zeilen() -> list[str]:
    """Die Datenzeilen der Tabelle — die einzige Wahrheit ueber die Laufzahl."""
    return [z for z in _messreihe().splitlines() if re.match(r"^\|\s*#\d+\s*\|", z)]


def _spalte(zeile: str, index: int) -> str:
    return [f.strip() for f in zeile.strip().strip("|").split("|")][index]


def test_die_tabelle_hat_ueberhaupt_zeilen():
    """Positivkontrolle zu allem, was unten folgt.

    Jede Zusicherung der Form «kein Widerspruch zur Tabelle» ist auch dann
    erfuellt, wenn die Tabelle leer ist oder das Muster nicht mehr passt —
    dann prueft sie nichts und bleibt gruen. Genau diese Falle hat im
    Portfolio schon vier tote Basispfade ein Release ueberleben lassen.
    """
    zeilen = _zeilen()
    assert len(zeilen) >= 10, f"nur {len(zeilen)} Tabellenzeilen gefunden — passt das Muster noch?"
    assert all(_spalte(z, 0).startswith("#") for z in zeilen)


@pytest.mark.parametrize("datei", ["messreihe", "claude_md"])
def test_kein_zaehler_widerspricht_der_tabelle(datei: str):
    """Befundart 1: «neun Laeufe» neben zehn Zeilen.

    Gesucht sind Wendungen, die eine Anzahl Laeufe behaupten — «elf Laeufe»,
    «elfmal durchgemessen», «alle elf Male», «sieben der elf». Der Nenner muss
    die Zeilenzahl sein; der Zaehler davor (die «sieben») bleibt Sache des
    Autors, denn er zaehlt etwas anderes.

    Grenze, ausgesprochen: «der zehnte Lauf» ist eine Ordnungszahl und meint
    einen bestimmten PR — die faengt dieses Muster absichtlich nicht.
    """
    text = _messreihe() if datei == "messreihe" else _claude_md()
    soll = len(_zeilen())

    woerter = "|".join(sorted(_ZAHLWORT, key=len, reverse=True))
    muster = re.compile(
        rf"\b(?:der|die|alle|nach)\s+({woerter})\s+(?:Läufe|Läufen)\b"
        rf"|\b({woerter})mal\s+durchgemessen\b",
        re.IGNORECASE,
    )

    falsch = []
    for treffer in muster.finditer(text):
        wort = (treffer.group(1) or treffer.group(2)).lower()
        if _ZAHLWORT[wort] != soll:
            falsch.append(treffer.group(0))

    assert not falsch, (
        f"{datei} behauptet {falsch}, die Tabelle hat aber {soll} Zeilen. "
        "Beim Eintragen einer Zeile ist jede abgeleitete Zahl nachzufuehren."
    )


def test_kein_einzelwert_der_tabelle_steht_in_der_prosa():
    """Befundart 2: `204 s` stand in der Prosa **und** in der Tabelle.

    Der Wert ist damit an zwei Stellen gepflegt und driftet bei der naechsten
    Korrektur. Geprueft werden die Laufzeit-Spalten; die Uhrzeiten nicht, denn
    die stehen ohnehin nur in der Tabelle und eine Uhrzeit als Regex faenge
    jede Tageszeit im Text.

    Ausgenommen sind **Spannen** der Form «X s bis … Y s». Eine Spanne ist
    kein Messwert, sondern der Schluss aus der Spalte; der Absatz in
    `CLAUDE.md` handelt von nichts anderem als davon, wie oft dieser Schluss
    schon kassiert wurde, und zitiert dafuer auch die kassierten Fassungen.
    Ohne die Zahlen waere er leer. Einzelwerte bleiben verboten — genau sie
    waren die Befunde.
    """
    zeilen = _zeilen()
    laufzeiten = {_spalte(z, 7) for z in zeilen} | {_spalte(z, 8) for z in zeilen}
    werte = set()
    for roh in laufzeiten:
        if treffer := re.search(r"(\d+(?:,\d+)?)\s*s", roh):
            werte.add(treffer.group(1))

    # Spannen zuerst herausschneiden, sonst meldet jede zitierte Fassung
    # ihre beiden Grenzen als Dublette.
    spanne = re.compile(r"\d+(?:,\d+)?\s*s\s+bis\s+(?:rund\s+)?\d+(?:,\d+)?\s*s")
    prosa_messreihe = "\n".join(z for z in _messreihe().splitlines() if not re.match(r"^\|", z))

    falsch = {}
    for datei, roh in (("CLAUDE.md", _claude_md()), ("messreihe", prosa_messreihe)):
        text = spanne.sub(" ", roh)
        treffer = sorted(w for w in werte if re.search(rf"\b{re.escape(w)}\s*s\b", text))
        if treffer:
            falsch[datei] = treffer

    assert not falsch, (
        f"Einzelwerte der Tabelle stehen zusaetzlich in der Prosa: {falsch}. "
        "Sie gehoeren nur in die Tabelle — auf die Zeile verweisen, nicht den "
        "Wert nennen. Ausgenommen sind nur Spannen der Form «X s bis Y s»."
    )


def test_die_abgeleitete_spanne_deckt_die_tabelle():
    """Befundart 3: eine Ableitung, welche die Tabelle ueberholt hat.

    `CLAUDE.md` nennt die Laufzeit-Spanne als Schluss aus der Messreihe. Fuenf
    Fassungen dieses Satzes sind nach oben korrigiert worden, viermal vom
    naechsten Lauf und zweimal von dem PR, der sie gerade eingetragen hatte.
    Hier faellt die sechste Korrektur als roter Check an, statt als Befund.
    """
    werte = []
    for zeile in _zeilen():
        for spalte in (_spalte(zeile, 7), _spalte(zeile, 8)):
            if treffer := re.search(r"(\d+(?:,\d+)?)\s*s", spalte):
                werte.append(float(treffer.group(1).replace(",", ".")))

    spanne = re.search(r"\*\*(\d+(?:,\d+)?)\s*s\s+bis\s+rund\s+(\d+(?:,\d+)?)\s*s\*\*", _claude_md())
    assert spanne, "CLAUDE.md nennt keine Laufzeit-Spanne mehr — dann ist dieser Test gegenstandslos"

    unten = float(spanne.group(1).replace(",", "."))
    oben = float(spanne.group(2).replace(",", "."))
    assert unten <= min(werte), f"die Spanne beginnt bei {unten} s, gemessen ist {min(werte)} s"
    assert oben >= max(werte), (
        f"die Spanne endet bei {oben} s, der langsamste Lauf braucht {max(werte)} s. "
        "Beim Eintragen einer Zeile ist die Spanne nachzufuehren."
    )


def test_claude_md_verweist_auf_die_messreihe():
    """Sonst laufen die beiden Dateien auseinander, ohne dass etwas rot wird.

    Die Trennung nimmt der Konventionen-Datei die Buchhaltung — sie darf ihr
    nicht den Verweis nehmen. Ohne ihn findet die naechste Sitzung die Zahlen
    nicht und legt eine zweite Reihe an.
    """
    assert "docs/codex-messreihe.md" in _claude_md(), (
        "CLAUDE.md verweist nicht mehr auf die Messreihe. Die Zahlen stehen "
        "dort; ohne Verweis sucht die naechste Sitzung sie hier und traegt sie "
        "erneut ein."
    )
