"""Der Protokoll-Pin muss die Revision nennen, die das SDK aushandelt.

`_app.py` prueft `PROTOCOL_VERSION not in SUPPORTED_PROTOCOL_VERSIONS` und
bricht beim Import ab, wenn die Revision fehlt. Das ist ein sinnvoller Schutz
gegen einen Wegfall — aber er kann eine Drift nicht erkennen:
`SUPPORTED_PROTOCOL_VERSIONS` ist rueckwaertskompatibel und enthaelt heute noch
`2024-11-05`. Der Pin stand auf `2025-06-18` und erfuellte die Pruefung
tadellos, waehrend das SDK laengst `2026-07-28` sprach.

Eine Mitgliedschaftspruefung gegen eine wachsende Liste kann nicht sagen, ob
man vorne oder hinten steht. Dieser Test sagt es.
"""

from __future__ import annotations

import re

from mcp.types import LATEST_PROTOCOL_VERSION
from mcp.types.version import SUPPORTED_PROTOCOL_VERSIONS

from srgssr_mcp._app import PROTOCOL_VERSION


def test_der_pin_nennt_die_revision_des_installierten_sdk() -> None:
    """Faellt, wenn ein SDK-Update die Protokollversion verschiebt.

    Die Loesung ist dann nicht, die Konstante blind nachzuziehen: erst das
    Spec-Changelog lesen, das Serververhalten pruefen, dann Konstante, README
    und `CHANGELOG.md` in einem Commit anheben.
    """
    assert PROTOCOL_VERSION == LATEST_PROTOCOL_VERSION, (
        f"gepinnt {PROTOCOL_VERSION}, das SDK handelt {LATEST_PROTOCOL_VERSION} aus"
    )


def test_die_mitgliedschaftspruefung_allein_wuerde_nicht_reichen() -> None:
    """Die Negativkontrolle fuer den Test darueber.

    Sie zeigt, warum er noetig ist: eine zwei Jahre alte Revision steht immer
    noch in `SUPPORTED_PROTOCOL_VERSIONS`, der Import-Schutz in `_app.py` liesse
    sie also anstandslos durch. Faellt dieser Test, hat das SDK die alten
    Revisionen entfernt — dann ist der Schutz dort tatsaechlich hinreichend und
    dieser Test darf weg.
    """
    assert "2025-06-18" in SUPPORTED_PROTOCOL_VERSIONS


def test_der_pin_ist_ein_datum_und_kein_bewegliches_ziel() -> None:
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", PROTOCOL_VERSION), PROTOCOL_VERSION
