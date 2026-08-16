"""Zugriff auf die aufgezeichneten Antworten und ihren Nachweis.

Eine Stelle, an der `tests/fixtures/` gelesen wird — sonst kennt jeder Test
seinen eigenen Pfad, und der Nachweis geht beim naechsten Umbenennen verloren.

Der Schluessel einer Aufzeichnung steht in `PROVENANCE.md` und nirgends sonst.
Das ist Absicht: der Nachweis ist damit nicht Beiwerk, sondern traegt den
Abspielbetrieb. Faellt er auseinander, faellt die Suite.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).resolve().parent / "fixtures"

#: Keine Aufzeichnung, sondern der Nachweis darueber.
_KEIN_FIXTURE = {"PROVENANCE.md"}


def recorded_names() -> list[str]:
    """Alle Aufzeichnungen im Ordner, ohne den Nachweis selbst."""
    return sorted(p.name for p in FIXTURES.iterdir() if p.name not in _KEIN_FIXTURE)


def fixture_text(name: str) -> str:
    pfad = FIXTURES / name
    if not pfad.exists():
        raise AssertionError(
            f"Keine Aufzeichnung unter {pfad}. Neu aufzeichnen ueber den Workflow "
            "«Fixtures aufzeichnen» — er hat die Credentials."
        )
    return pfad.read_text(encoding="utf-8")


def fixture_json(name: str) -> Any:
    return json.loads(fixture_text(name))


@lru_cache(maxsize=1)
def provenance() -> str:
    return (FIXTURES / "PROVENANCE.md").read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def schluesselverzeichnis() -> dict[str, str]:
    """Schluessel (volle URL) → Dateiname, gelesen aus `PROVENANCE.md`."""
    verzeichnis: dict[str, str] = {}
    for block in provenance().split("## `")[1:]:
        datei = block.split("`", 1)[0]
        treffer = re.search(r"\*\*Schluessel:\*\* `([^`]+)`", block)
        if treffer:
            verzeichnis[treffer.group(1)] = datei
    return verzeichnis


def schluessel_fuer(request: Any) -> str:
    """Woran eine Anfrage beim Abspielen wiedererkannt wird — wie im Recorder.

    Bewusst dieselbe Regel wie in `scripts/record_fixtures.py`, und bewusst
    ohne jeden Header: bei dieser API traegt die Anfrage ans Token-Endpunkt
    `Authorization: Basic <key:secret>`.
    """
    return str(request.url)
