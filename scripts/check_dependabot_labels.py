#!/usr/bin/env python3
"""Prueft, dass jedes von `dependabot.yml` verlangte Label im Repo existiert.

Dependabot haengt an jeden PR die Labels, die in `.github/dependabot.yml` unter
`labels:` stehen. Existiert eines davon nicht, legt Dependabot es *nicht* an —
es kommentiert stattdessen an jedem erzeugten PR:

    The following labels could not be found: `dependencies`.
    Please create it before Dependabot can add it to a pull request.

Der PR entsteht trotzdem, die CI bleibt gruen, und die Meldung sieht aus wie
Rauschen. Genau so ist es passiert: am 28.8.2026 verlangten 24 Repos des
Portfolios zusammen 50 Labels, und **50 davon fehlten** — einzeln nachgemessen.
Aufgefallen ist es an einem Kommentar unter einem Dependabot-PR, nicht an einem
roten Lauf. Eine Deklaration, die niemand vergleicht, schuetzt vor nichts.

Dieser Check macht aus der Konvention ein Gate.

Verwendung:
    python scripts/check_dependabot_labels.py     # exit 1 bei fehlendem Label

Bewusst nur Standardbibliothek und kein YAML-Parser: fuenf Server im Portfolio
fahren ihre CI auch auf Python 3.10, und `pyyaml` gehoert nirgends zu den
Laufzeit-Abhaengigkeiten. Gelesen wird deshalb zeilenweise — die Extraktion ist
gegen alle 31 echten `dependabot.yml` des Portfolios gegengeprueft.

**Ohne Token wird nichts stillschweigend gruen.** In der CI (Umgebungsvariable
`CI`) ist ein fehlender Token ein Fehler, kein Ueberspringen — sonst waere das
Gate genau die Attrappe, die es verhindern soll. Lokal, ohne Token, prueft es
nur die Deklaration und sagt das ausdruecklich.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# `.yml` zuerst, weil GitHub das so dokumentiert; `.yaml` wird trotzdem gelesen,
# damit die Schreibweise nicht ueber das Ergebnis entscheidet.
CONFIGS = (".github/dependabot.yml", ".github/dependabot.yaml")

# Ein Listeneintrag unterhalb von `labels:`. Die Einrueckung muss groesser sein
# als die von `labels:` selbst — sonst zaehlten die Nachbarschluessel mit, deren
# Werte ebenfalls in Anfuehrungszeichen stehen (`directory: "/"`, `interval:
# "monthly"`). Ein naiver Griff nach allen Zeichenketten in der Naehe hat genau
# das getan und `/` als Label gemeldet.
_ITEM = re.compile(r"^(\s*)-\s*(.+?)\s*$")
_LABELS_BLOCK = re.compile(r"^(\s*)labels:\s*$")
_LABELS_INLINE = re.compile(r"^\s*labels:\s*\[(.*)\]\s*$")

_API = "https://api.github.com"


def _entwerte(rohwert: str) -> str:
    return rohwert.strip().strip("\"'")


def declared_labels(text: str) -> set[str]:
    """Die Labels, die diese Konfiguration verlangt — Block- und Inline-Form."""
    lines = text.splitlines()
    found: set[str] = set()
    i = 0
    while i < len(lines):
        inline = _LABELS_INLINE.match(lines[i])
        if inline:
            found.update(_entwerte(t) for t in inline.group(1).split(",") if t.strip())
            i += 1
            continue
        block = _LABELS_BLOCK.match(lines[i])
        if not block:
            i += 1
            continue
        indent = len(block.group(1))
        j = i + 1
        while j < len(lines):
            if not lines[j].strip():
                j += 1
                continue
            item = _ITEM.match(lines[j])
            if item and len(item.group(1)) > indent:
                found.update({_entwerte(item.group(2))})
                j += 1
                continue
            break
        i = j
    return {label for label in found if label}


def config_text() -> str | None:
    """Der Inhalt der Dependabot-Konfiguration, oder None, wenn es keine gibt."""
    for name in CONFIGS:
        path = ROOT / name
        if path.exists():
            return path.read_text(encoding="utf-8")
    return None


def repo_slug() -> str | None:
    """`owner/repo` — in der CI aus der Umgebung, sonst aus dem Remote."""
    from_env = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if from_env:
        return from_env
    try:
        url = subprocess.run(
            ["git", "-C", str(ROOT), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    match = re.search(r"[:/]([^/:]+/[^/]+?)(?:\.git)?$", url)
    return match.group(1) if match else None


def existing_labels(slug: str, token: str) -> set[str]:
    """Alle Labels des Repos.

    Blaettert: ohne das faende ein Repo mit ueber 100 Labels die spaeteren nicht,
    und das Gate meldete ein vorhandenes Label als fehlend.
    """
    names: set[str] = set()
    page = 1
    while True:
        request = urllib.request.Request(
            f"{_API}/repos/{slug}/labels?per_page=100&page={page}",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "User-Agent": "check-dependabot-labels",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            batch = json.load(response)
        if not batch:
            return names
        names.update(str(entry["name"]) for entry in batch)
        if len(batch) < 100:
            return names
        page += 1


def token_from_env() -> str:
    for name in ("GH_TOKEN", "GITHUB_TOKEN"):
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def main() -> int:
    text = config_text()
    if text is None:
        print("Keine .github/dependabot.yml — nichts zu pruefen.")
        return 0

    declared = declared_labels(text)
    if not declared:
        print("dependabot.yml verlangt keine Labels — nichts zu pruefen.")
        return 0

    verlangt = ", ".join(sorted(declared))
    token = token_from_env()
    if not token:
        if os.environ.get("CI"):
            fehlt = "Kein GH_TOKEN/GITHUB_TOKEN in der CI — nichts pruefbar."
            hinweis = "Im Workflow setzen: GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}"
            print(f"{fehlt}\n{hinweis}", file=sys.stderr)
            return 1
        print(f"dependabot.yml verlangt: {verlangt}")
        print("Kein Token vorhanden — nur die Deklaration geprueft, nicht das Repo.")
        return 0

    slug = repo_slug()
    if slug is None:
        wo = "weder GITHUB_REPOSITORY noch Remote"
        print(f"Repo nicht bestimmbar ({wo}).", file=sys.stderr)
        return 1

    try:
        vorhanden = existing_labels(slug, token)
    except (urllib.error.URLError, OSError, ValueError, KeyError) as fehler:
        print(f"Labels von {slug} nicht abrufbar: {fehler}", file=sys.stderr)
        return 1

    fehlend = sorted(declared - vorhanden)
    if not fehlend:
        print(f"Dependabot-Labels vollstaendig ({verlangt}) in {slug}.")
        return 0

    kopf = f"dependabot.yml verlangt Labels, die in {slug} nicht existieren:"
    print(kopf, file=sys.stderr)
    for label in fehlend:
        print(f"  - {label}", file=sys.stderr)
    # Keine impliziten String-Verkettungen ueber mehrere Zeilen: im Portfolio
    # stehen line-length 88, 100, 110 und 120 nebeneinander, und `ruff format`
    # zieht einen Ausdruck zusammen, sobald er in die jeweilige Breite passt.
    # Was hier auf zwei Zeilen gehoert, waere anderswo eine — und
    # `ruff format --check` fiele beim Kopieren um. Lange Meldungen bekommen
    # deshalb eine lokale Variable.
    folge = "Dependabot legt sie nicht selbst an; es kommentiert an jedem PR."
    wie = "Anlegen mit:"
    zeilen = (f"    gh label create {label} --repo {slug}" for label in fehlend)
    befehle = "\n".join(zeilen)
    print(f"\n{folge}\n{wie}\n{befehle}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
