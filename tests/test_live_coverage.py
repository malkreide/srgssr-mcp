"""Die Live-Suite muss jedes Werkzeug anfassen — sie ist hier das Drift-Signal.

Die Portfolio-Konvention verlangt aufgezeichnete Antworten je externem Endpunkt:
handgeschriebene Fixtures kodieren die Annahme ihres Autors und koennen sie
nicht widerlegen. Dieser Server kann sie nicht liefern. Die SRG-SSR-API laesst
ohne Consumer Key nichts durch — der Token-Endpunkt antwortet mit 401, und alle
fuenf Produkt-Basen (`srf-meteo`, `videometadata`, `audiometadata`, `epg`,
`polis-api`) ebenso. Ohne Zugangsdaten gibt es keine echte Erfolgs-Antwort zum
Aufzeichnen, und eine 401 als Fixture abzulegen hiesse, sie als das auszugeben,
was die Quelle normalerweise sagt.

Was an ihre Stelle tritt, ist der naechtliche Live-Lauf: er haelt echte
Antworten gegen die Felder, aus denen dieser Server liest, und meldet sich bei
Rot per Issue. Das ist das staerkere Signal — es prueft die Quelle von heute
statt eine Aufzeichnung von damals —, aber nur, solange es *jedes* Werkzeug
erreicht. Ein Werkzeug ohne Live-Test hat dann gar keine Deckung gegen Drift:
weder Aufzeichnung noch Vertragspruefung.

Genau das war der Fall. `srgssr_daily_briefing` fehlte in der Live-Suite —
ausgerechnet das Werkzeug, das ueber zwei Produkte hinweg zusammenfuehrt und
damit an den meisten Stellen brechen kann.
"""

from __future__ import annotations

import pathlib
import re

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_TOOLS_DIR = _ROOT / "src" / "srgssr_mcp" / "tools"
_LIVE = _ROOT / "tests" / "test_live.py"


def _werkzeuge() -> set[str]:
    """Die Werkzeugnamen aus dem Quellcode — nicht aus einer gepflegten Liste.

    Eine Liste danebenzulegen hiesse, sie beim naechsten Werkzeug zu vergessen;
    dann waere der Test gruen und die Deckung trotzdem unvollstaendig.
    """
    namen: set[str] = set()
    for pfad in _TOOLS_DIR.glob("*.py"):
        namen |= set(re.findall(r"^async def (srgssr_\w+)\(", pfad.read_text(), re.MULTILINE))
    return namen


def test_der_quellcode_nennt_ueberhaupt_werkzeuge():
    """Sonst ist die Zusicherung unten leer und faellt nie.

    Ein Suchmuster, das nichts findet, laesst jede Aussage darueber wahr werden.
    """
    gefunden = _werkzeuge()
    assert len(gefunden) >= 10, f"nur {len(gefunden)} Werkzeuge gefunden: {sorted(gefunden)}"


def test_jedes_werkzeug_steht_in_der_live_suite():
    """Ohne Aufzeichnungen ist der naechtliche Lauf die einzige Drift-Pruefung.

    Ein Werkzeug, das er nicht anfasst, hat gar keine: seine Felder koennen sich
    in der Quelle aendern, ohne dass irgendetwas rot wird.
    """
    live = _LIVE.read_text()
    fehlend = sorted(w for w in _werkzeuge() if w not in live)
    assert not fehlend, (
        f"ohne Live-Test und damit ohne jede Drift-Deckung: {fehlend}. "
        "Dieser Server hat keine aufgezeichneten Fixtures (Zugangsdaten "
        "erforderlich) — der naechtliche Lauf ist das einzige Signal."
    )
