#!/usr/bin/env python3
"""Zeichnet je eine echte Antwort pro Abfrage auf.

Warum nicht von Hand geschrieben: eine handgeschriebene Erfolgs-Antwort stimmt
mit dem ueberein, was ihr Autor annahm, und kann die Quelle deshalb nicht
widerlegen. Aufgezeichnet wird darum an demselben Ort, an dem der Server die
Antwort entgegennimmt — ueber einen httpx-Response-Hook auf dem geteilten
Client aus `_http._get_http_client()`. Damit tragen Aufzeichnung und Betrieb
denselben User-Agent, dasselbe Timeout und dieselbe Retry-Mechanik.

Fuenf API-Familien, aber deutlich mehr Abfrageformen: `srgssr_weather_*` faechert
ueber `_query_variants` in mehrere Suchen auf, `srgssr_daily_briefing` spannt
EPG und Wetter zugleich, und drei Werkzeuge brauchen eine ID, die es sich vorher
selbst holt. Die Portfolio-Regel «eine Antwort je externem Endpunkt» waere mit
fuenf Dateien erfuellt und truege fast nichts.

Zugeordnet wird beim Abspielen nach der Anfrage und nicht nach der Reihenfolge:
`srgssr_daily_briefing` startet seine Abrufe nebenlaeufig, und die Reihenfolge,
in der sie zurueckkommen, ist keine Zusicherung.

## Das Token wird nie aufgezeichnet

Diese API ist die einzige im Portfolio mit OAuth2. Die Antwort von
`/oauth/v1/accesstoken` traegt ein **gueltiges Bearer-Token**, und die Anfrage
dorthin traegt `Authorization: Basic <key:secret>`. Beides gehoert nicht in ein
Repository. Deshalb:

* Der Hook legt ausschliesslich **Antwort-Rumpfe** ab — nie einen Header, weder
  den der Anfrage noch den der Antwort.
* Die Token-URL ist hart ausgenommen (:data:`NIE_AUFZEICHNEN`) und taucht auch
  als Schluessel nicht auf.
* Vor dem Schreiben laeuft :func:`_pruefe_kein_geheimnis` ueber jede Datei und
  bricht ab, wenn Token, Key oder Secret darin vorkommen. Ein Abbruch ist hier
  richtig: eine halb geschriebene Aufzeichnung ist reparierbar, ein
  veroeffentlichtes Token nicht.

## Aufruf

    SRGSSR_CONSUMER_KEY=… SRGSSR_CONSUMER_SECRET=… \\
        PYTHONPATH=src python scripts/record_fixtures.py

Ohne Credentials bricht der Lauf sofort und mit Begruendung ab — er kann von
hier aus nicht laufen, wohl aber dort, wo die Credentials schon liegen: der
Workflow `.github/workflows/record-fixtures.yml` faehrt genau diesen Befehl mit
denselben Secrets wie die naechtliche Live-Suite.

Schreibt nach `tests/fixtures/` und erzeugt `tests/fixtures/PROVENANCE.md` neu.
Dateien, die kein Plan-Eintrag mehr erzeugt, werden geloescht — sonst waechst
der Ordner und der Nachweis bleibt zurueck.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL / "src"))

from srgssr_mcp import _http, server  # noqa: E402
from srgssr_mcp._app import BusinessUnit  # noqa: E402
from srgssr_mcp._models import ToolErrorResponse  # noqa: E402
from srgssr_mcp.tools import polis  # noqa: E402

FIXTURES = WURZEL / "tests" / "fixtures"

VERSUCHE = 3

# Der Backoff-Schlaf unter eigenem Namen. Ein Test, der `asyncio.sleep` selbst
# patcht, greift ins fremde Modul und entschaerft die Mechanik im ganzen
# Prozess; ueber den Alias trifft er genau diese Schleife.
_sleep = asyncio.sleep

# Wie viele Eintraege einer Trefferliste bleiben. Die Form einer Zeile belegen
# drei genauso gut wie hundert; die Zahl steht je Datei im Nachweis.
ZEILEN = 3

#: Platzhalter fuer Felder, die erst zur Laufzeit feststehen. Sichtbar statt
#: leer: ein `""` faellt an der Modell-Validierung auf, aber erst mit einer
#: Meldung ueber die Mindestlaenge — die sagt nicht, dass hier eine ID fehlt.
#: `_mit_laufzeitwerten` prueft, dass keiner uebrig bleibt.
ZUR_LAUFZEIT = "<zur-laufzeit>"

#: Antworten von diesen URLs werden nie abgelegt und nie zu einem Schluessel.
#: Der Rumpf der Token-Antwort ist ein gueltiges Bearer-Token.
NIE_AUFZEICHNEN = (_http.TOKEN_URL,)


@dataclass(frozen=True)
class Aufruf:
    """Ein Werkzeugaufruf, der Anfragen ausloesen soll."""

    name: str
    werkzeug: str
    klasse: str
    eingabe: dict[str, Any]
    # Kuerzen ist nur dort harmlos, wo der Server die Liste ganz liest. Sucht
    # er *in* ihr — oder holt er zu jedem Eintrag eine weitere Antwort —, dann
    # schneidet ein Schnitt womoeglich genau die Zeile weg, die er braucht.
    kuerzen: bool = True
    notiz: str = ""


# Die Eingaben stammen aus `tests/test_live.py`, nicht aus einer neuen
# Erfindung: die Live-Suite faehrt sie naechtlich gegen die echte API, es ist
# also belegt, dass sie Treffer liefern. Klein gehalten (`page_size=3..5`), denn
# jede Zeile mehr blaeht den Ordner, ohne die Satzform besser zu belegen.
#
# Drei Aufrufe brauchen eine ID, die `main()` zur Laufzeit besorgt — genauso wie
# die Live-Suite sie sich holt. Eine fest eingetragene ID waere in ein paar
# Wochen ein toter Verweis, und die Aufzeichnung schwiege darueber.
PLAN: list[Aufruf] = [
    # --- Wetter -----------------------------------------------------------
    Aufruf(
        "weather_search",
        "srgssr_weather_search_location",
        "WeatherSearchInput",
        {"query": "Zürich"},
        notiz="Faechert ueber `_query_variants` auf — mehrere Suchen je Aufruf.",
    ),
    Aufruf(
        "weather_current",
        "srgssr_weather_current",
        "WeatherForecastInput",
        {"latitude": 47.3769, "longitude": 8.5417},
    ),
    Aufruf(
        "weather_24h",
        "srgssr_weather_forecast_24h",
        "WeatherForecastInput",
        {"latitude": 47.3769, "longitude": 8.5417},
    ),
    Aufruf(
        "weather_7day",
        "srgssr_weather_forecast_7day",
        "WeatherForecastInput",
        {"latitude": 47.3769, "longitude": 8.5417},
    ),
    # --- Video ------------------------------------------------------------
    Aufruf(
        "video_shows",
        "srgssr_video_get_shows",
        "VideoShowsInput",
        {"business_unit": BusinessUnit.SRF, "character_filter": "t", "page_size": 5},
    ),
    Aufruf(
        "video_livestreams",
        "srgssr_video_get_livestreams",
        "VideoLivestreamsInput",
        {"business_unit": BusinessUnit.SRF},
    ),
    Aufruf(
        "video_episodes",
        "srgssr_video_get_episodes",
        "VideoEpisodesInput",
        # `show_id` setzt `main()` zur Laufzeit.
        {"business_unit": BusinessUnit.SRF, "show_id": ZUR_LAUFZEIT, "page_size": 3},
    ),
    # --- Audio ------------------------------------------------------------
    Aufruf(
        "audio_livestreams",
        "srgssr_audio_get_livestreams",
        "VideoLivestreamsInput",
        {"business_unit": BusinessUnit.SRF},
    ),
    Aufruf(
        "audio_shows",
        "srgssr_audio_get_shows",
        "AudioShowsInput",
        # `channel_id` setzt `main()` zur Laufzeit — die v2-Liste ist je Kanal.
        {"business_unit": BusinessUnit.SRF, "channel_id": ZUR_LAUFZEIT, "character_filter": "e", "page_size": 5},
    ),
    Aufruf(
        "audio_episodes",
        "srgssr_audio_get_episodes",
        "AudioEpisodesInput",
        {"business_unit": BusinessUnit.SRF, "show_id": ZUR_LAUFZEIT, "page_size": 3},
    ),
    # --- EPG --------------------------------------------------------------
    Aufruf(
        "epg_programs",
        "srgssr_epg_get_programs",
        "EpgProgramsInput",
        # `date` setzt `main()` auf gestern — ein fixes Datum faellt aus dem
        # Fenster, das die API vorhaelt.
        {"business_unit": BusinessUnit.SRF, "channel_id": "srf-1", "date": ZUR_LAUFZEIT},
    ),
    # --- Polis ------------------------------------------------------------
    Aufruf(
        "polis_votations",
        "srgssr_polis_get_votations",
        "PolisListInput",
        {"year_from": 2020, "year_to": 2024, "page_size": 5},
        kuerzen=False,
        notiz="Ungekuerzt: der Server filtert und zaehlt *in* diesen Listen.",
    ),
    Aufruf(
        "polis_elections",
        "srgssr_polis_get_elections",
        "PolisListInput",
        {"year_from": 2020, "year_to": 2024, "page_size": 5},
        kuerzen=False,
        notiz="Ungekuerzt: der Server filtert und zaehlt *in* diesen Listen.",
    ),
    Aufruf(
        "polis_results",
        "srgssr_polis_get_votation_results",
        "PolisResultInput",
        # `votation_id` setzt `main()` zur Laufzeit.
        {"votation_id": ZUR_LAUFZEIT},
    ),
    # --- Aggregation ------------------------------------------------------
    Aufruf(
        "daily_briefing",
        "srgssr_daily_briefing",
        "DailyBriefingInput",
        {
            "business_unit": BusinessUnit.SRF,
            "channel_id": "srf-1",
            "date": ZUR_LAUFZEIT,
            "latitude": 47.37,
            "longitude": 8.54,
        },
        kuerzen=False,
        notiz="Ungekuerzt: spannt EPG und Wetter nebenlaeufig, beide Haelften zaehlen.",
    ),
]


def schluessel_fuer(request: httpx.Request) -> str:
    """Woran eine Anfrage beim Abspielen wiedererkannt wird.

    Die volle URL samt Query. Der Hostname bleibt drin, obwohl dieser Server nur
    einen Host anspricht: die Basispfade der fuenf Produkte unterscheiden sich
    erst hinter ihm, und ein Schluessel ohne Host waere beim naechsten Produkt
    still mehrdeutig.

    Kein Header geht ein. Bei dieser API traegt die Anfrage an das
    Token-Endpunkt `Authorization: Basic <key:secret>`; ein Schluessel, der
    Header mitnimmt, haette das Geheimnis in den Nachweis geschrieben.
    """
    return str(request.url)


def _ist_gesperrt(url: str) -> bool:
    """True fuer Antworten, die nie in den Ordner duerfen (Token)."""
    return any(url.startswith(gesperrt) for gesperrt in NIE_AUFZEICHNEN)


def _endung(text: str) -> str:
    """`.json`, wenn die Antwort JSON ist — sonst `.txt`."""
    try:
        json.loads(text)
    except json.JSONDecodeError:
        return ".txt"
    return ".json"


@dataclass
class Antwort:
    """Eine gesehene Antwort samt der Anfrage, die sie ausgeloest hat."""

    schluessel: str
    text: str
    werkzeuge: list[str] = field(default_factory=list)
    darf_kuerzen: bool = True
    notiz: str = ""
    dateiname: str = ""
    original_bytes: int = 0
    gekuerzt_von: int = 0
    behalten: int = 0
    sha256: str = ""
    bytes: int = 0


def _hook_fuer(gesehen: list[Antwort]) -> Callable[[httpx.Response], Awaitable[None]]:
    """Baut den Response-Hook fuer einen Versuch.

    Eigene Funktion, damit die Liste als Argument gebunden ist und nicht als
    Schleifenvariable aus dem umgebenden Namensraum (ruff B023).
    """

    async def hook(response: httpx.Response) -> None:
        await response.aread()
        url = str(response.request.url)
        if _ist_gesperrt(url):
            # Der Rumpf ist ein gueltiges Bearer-Token. Nicht ablegen, nicht
            # als Schluessel fuehren, nicht in den Nachweis.
            return
        if response.status_code >= 400:
            # Eine Fehlerantwort als Fixture abzulegen hiesse, sie als das
            # auszugeben, was die Quelle normalerweise sagt.
            print(
                f"– nicht aufgezeichnet (HTTP {response.status_code}): {url}",
                file=sys.stderr,
            )
            return
        gesehen.append(Antwort(schluessel=schluessel_fuer(response.request), text=response.text))

    return hook


def _leere_caches() -> None:
    """Ohne das beantwortet ein Prozess-Cache den zweiten Versuch ohne Anfrage.

    Polis haelt Kantons- und Fall-Listen modulweit; ein Wiederholungsversuch
    saehe dann «keine Anfrage abgeschickt» und der Aufruf fiele als kaputt auf,
    obwohl er es nicht ist. Das Token-Caching bleibt bewusst stehen: ein
    zusaetzlicher Refresh brachte nur eine weitere Anfrage, die ohnehin nicht
    aufgezeichnet wird.
    """
    polis._clear_reference_cache()


async def _fahre(a: Aufruf) -> list[Antwort]:
    """Ruft ein Werkzeug und gibt die dabei gesehenen Antworten zurueck."""
    fn = getattr(server, a.werkzeug)
    modell = getattr(server, a.klasse)(**a.eingabe)
    letzter: Exception | None = None

    for versuch in range(VERSUCHE):
        if versuch:
            await _sleep(2**versuch)
        _leere_caches()
        gesehen: list[Antwort] = []
        hook = _hook_fuer(gesehen)
        client = await _http._get_http_client()
        client.event_hooks.setdefault("response", []).append(hook)
        try:
            ergebnis = await fn(modell)
        except Exception as e:  # noqa: BLE001 — jeder Fehler ist hier ein Retry-Grund
            letzter = e
            continue
        finally:
            client.event_hooks["response"].remove(hook)

        if isinstance(ergebnis, ToolErrorResponse):
            # Die Werkzeuge geben seit SDK-002 typisierte Modelle zurueck. Auf
            # einen Fehlerstring zu pruefen kann gegen ein BaseModel nie
            # zutreffen — genau dieser Fehler hat die Live-Suite einmal
            # dekorativ gemacht.
            letzter = RuntimeError(f"{a.werkzeug} meldet: {ergebnis.error[:200]}")
            continue
        if not gesehen:
            letzter = RuntimeError(f"{a.werkzeug} hat keine Anfrage abgeschickt")
            continue
        for antwort in gesehen:
            antwort.werkzeuge.append(a.werkzeug)
            antwort.darf_kuerzen = a.kuerzen
            antwort.notiz = a.notiz
        return gesehen

    raise RuntimeError(f"{a.name} nach {VERSUCHE} Versuchen nicht aufgezeichnet: {letzter}")


def _kuerze(daten: Any) -> tuple[int, int, Any]:
    """Kuerzt jede Liste im Baum auf `ZEILEN`; gibt (vorher, nachher, Daten).

    Nur die Zahl der Eintraege, nie ein Feld. Zaehlfelder daneben bleiben
    stehen: die Quelle meint damit die Gesamtzahl und nicht die Zahl der
    gelieferten Zeilen, und genau die liest der Server aus.
    """
    vorher = nachher = 0

    def geh(knoten: Any) -> Any:
        nonlocal vorher, nachher
        if isinstance(knoten, dict):
            return {k: geh(v) for k, v in knoten.items()}
        if isinstance(knoten, list):
            vorher += len(knoten)
            gekuerzt = knoten[:ZEILEN]
            nachher += len(gekuerzt)
            return [geh(v) for v in gekuerzt]
        return knoten

    # Erst laufen lassen, dann die Zaehler lesen. `return vorher, nachher,
    # geh(daten)` wertet von links nach rechts aus und lieferte deshalb immer
    # (0, 0) — der Nachweis schriebe «ungekuerzt» ueber jede gekuerzte Datei.
    ergebnis = geh(daten)
    return vorher, nachher, ergebnis


def _geheimnisse() -> list[str]:
    """Die Zeichenketten, die in keiner Datei stehen duerfen.

    Key und Secret aus der Umgebung, und das Token, das der Lauf sich geholt
    hat. Leere Werte fallen raus — sonst waere die Pruefung unten trivial wahr
    fuer jede Datei.
    """
    kandidaten = [
        os.environ.get("SRGSSR_CONSUMER_KEY", ""),
        os.environ.get("SRGSSR_CONSUMER_SECRET", ""),
        _http._token_cache.get("access_token") or "",
    ]
    return [k for k in kandidaten if k]


def _pruefe_kein_geheimnis(text: str, woher: str) -> None:
    """Bricht ab, wenn ein Geheimnis in einer zu schreibenden Datei steht.

    Abbruch und nicht Warnung: eine halb geschriebene Aufzeichnung laesst sich
    wiederholen, ein veroeffentlichtes Token nicht zurueckholen.
    """
    for geheim in _geheimnisse():
        if geheim in text:
            raise SystemExit(
                f"ABBRUCH: {woher} enthaelt ein Geheimnis (Token, Key oder Secret). Es wurde nichts geschrieben."
            )


async def _erste_id(werkzeug: str, klasse: str, eingabe: dict[str, Any], feld: str) -> str:
    """Holt die erste ID einer Liste — so, wie die Live-Suite es auch tut."""
    ergebnis = await getattr(server, werkzeug)(getattr(server, klasse)(**eingabe))
    if isinstance(ergebnis, ToolErrorResponse):
        raise RuntimeError(f"{werkzeug} liefert einen Fehler: {ergebnis.error[:200]}")
    eintraege = getattr(ergebnis, feld, None) or []
    if not eintraege:
        raise RuntimeError(f"{werkzeug} liefert keine {feld} — keine ID zu holen")
    kennung = eintraege[0].id
    if not kennung:
        raise RuntimeError(f"{werkzeug}.{feld}[0] traegt keine id — Schema-Drift?")
    return str(kennung)


async def _laufzeitwerte() -> dict[str, dict[str, Any]]:
    """Die IDs und das Datum, die erst zur Laufzeit feststehen."""
    from datetime import date, timedelta

    gestern = (date.today() - timedelta(days=1)).isoformat()

    show_id = await _erste_id(
        "srgssr_video_get_shows",
        "VideoShowsInput",
        {"business_unit": BusinessUnit.SRF, "character_filter": "t", "page_size": 5},
        "shows",
    )
    kanal_id = await _erste_id(
        "srgssr_audio_get_livestreams",
        "VideoLivestreamsInput",
        {"business_unit": BusinessUnit.SRF},
        "channels",
    )
    audio_show_id = await _erste_id(
        "srgssr_audio_get_shows",
        "AudioShowsInput",
        {"business_unit": BusinessUnit.SRF, "channel_id": kanal_id, "page_size": 5},
        "shows",
    )
    abstimmung_id = await _erste_id(
        "srgssr_polis_get_votations",
        "PolisListInput",
        {"year_from": 2020, "year_to": 2024, "page_size": 5},
        "votations",
    )
    print(
        f"Zur Laufzeit ermittelt: show={show_id} kanal={kanal_id} "
        f"audio_show={audio_show_id} abstimmung={abstimmung_id} datum={gestern}",
        file=sys.stderr,
    )
    return {
        "video_episodes": {"show_id": show_id},
        "audio_shows": {"channel_id": kanal_id},
        "audio_episodes": {"show_id": audio_show_id},
        "polis_results": {"votation_id": abstimmung_id},
        "epg_programs": {"date": gestern},
        "daily_briefing": {"date": gestern},
    }


def _mit_laufzeitwerten(plan: list[Aufruf], werte: dict[str, dict[str, Any]]) -> list[Aufruf]:
    """Setzt die zur Laufzeit ermittelten Felder in die Plan-Eintraege ein.

    Bleibt ein Platzhalter uebrig, bricht das hier ab und nicht spaeter in der
    Modell-Validierung: dort haette es «String should have at least 1
    character» geheissen — richtig, aber es sagt nicht, dass eine ID nicht
    besorgt wurde.
    """
    fertig = []
    for a in plan:
        zusatz = werte.get(a.name)
        if zusatz:
            a = Aufruf(a.name, a.werkzeug, a.klasse, {**a.eingabe, **zusatz}, a.kuerzen, a.notiz)
        offen = [k for k, v in a.eingabe.items() if v == ZUR_LAUFZEIT]
        if offen:
            raise RuntimeError(
                f"{a.name}: {', '.join(offen)} steht noch auf {ZUR_LAUFZEIT!r} — "
                "`_laufzeitwerte` liefert dafuer nichts."
            )
        fertig.append(a)
    return fertig


async def main() -> int:
    if not (os.environ.get("SRGSSR_CONSUMER_KEY") and os.environ.get("SRGSSR_CONSUMER_SECRET")):
        print(
            "SRGSSR_CONSUMER_KEY und SRGSSR_CONSUMER_SECRET sind nicht gesetzt.\n"
            "Ohne sie antwortet api.srgssr.ch mit HTTP 401 — der Host ist erreichbar,\n"
            "es fehlen allein die Credentials. Der Workflow\n"
            "`.github/workflows/record-fixtures.yml` faehrt diesen Befehl mit denselben\n"
            "Secrets wie die naechtliche Live-Suite.",
            file=sys.stderr,
        )
        return 2

    FIXTURES.mkdir(parents=True, exist_ok=True)
    heute = datetime.now(UTC).date().isoformat()
    nach_schluessel: dict[str, Antwort] = {}
    zaehler: dict[str, int] = {}

    try:
        aufrufe = _mit_laufzeitwerten(PLAN, await _laufzeitwerte())
        for a in aufrufe:
            print(f"… {a.werkzeug} ({a.name})", file=sys.stderr)
            for antwort in await _fahre(a):
                if antwort.schluessel in nach_schluessel:
                    vorhanden = nach_schluessel[antwort.schluessel]
                    if a.werkzeug not in vorhanden.werkzeuge:
                        vorhanden.werkzeuge.append(a.werkzeug)
                    continue
                zaehler[a.name] = zaehler.get(a.name, 0) + 1
                antwort.dateiname = f"{a.name}_{zaehler[a.name]}{_endung(antwort.text)}"
                nach_schluessel[antwort.schluessel] = antwort
    finally:
        await _http.close_http_client()

    # Erst pruefen, dann schreiben. Nichts landet auf der Platte, bevor jede
    # Aufzeichnung und jeder Schluessel gegen die Geheimnisse gehalten wurde.
    for antwort in nach_schluessel.values():
        _pruefe_kein_geheimnis(antwort.text, antwort.dateiname)
        _pruefe_kein_geheimnis(antwort.schluessel, f"Schluessel von {antwort.dateiname}")

    for antwort in nach_schluessel.values():
        antwort.original_bytes = len(antwort.text.encode("utf-8"))
        try:
            daten = json.loads(antwort.text)
        except json.JSONDecodeError:
            (FIXTURES / antwort.dateiname).write_text(antwort.text, encoding="utf-8")
        else:
            if antwort.darf_kuerzen:
                antwort.gekuerzt_von, antwort.behalten, daten = _kuerze(daten)
            # Neu eingerueckt geschrieben: eine Zeile JSON waere kleiner, aber
            # im Diff nicht lesbar, und ein Fixture will gelesen werden.
            (FIXTURES / antwort.dateiname).write_text(
                json.dumps(daten, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
        roh = (FIXTURES / antwort.dateiname).read_bytes()
        antwort.sha256 = hashlib.sha256(roh).hexdigest()
        antwort.bytes = len(roh)

    antworten = sorted(nach_schluessel.values(), key=lambda x: x.dateiname)
    _schreibe_provenance(antworten, heute)

    # Aufraeumen: was kein Plan-Eintrag mehr erzeugt, hat auch keinen Nachweis.
    geschrieben = {a.dateiname for a in antworten} | {"PROVENANCE.md"}
    for pfad in sorted(FIXTURES.iterdir()):
        if pfad.name not in geschrieben:
            print(f"– entferne veraltet: {pfad.name}", file=sys.stderr)
            pfad.unlink()

    print(f"{len(antworten)} Aufzeichnungen in {FIXTURES}", file=sys.stderr)
    return 0


def _schreibe_provenance(antworten: list[Antwort], heute: str) -> None:
    zeilen = [
        "# Herkunft der Fixtures",
        "",
        f"Aufgezeichnet am **{heute}** mit `PYTHONPATH=src python scripts/record_fixtures.py`.",
        "",
        "Eine Antwort je **Abfrage**, nicht je Endpunkt: `srgssr_weather_search_location`",
        "faechert ueber `_query_variants` in mehrere Suchen auf, `srgssr_daily_briefing`",
        "spannt EPG und Wetter zugleich, und drei Werkzeuge holen sich vorher eine ID.",
        "Fuenf Dateien wuerden die Portfolio-Regel erfuellen und fast nichts belegen.",
        "",
        "Der **Schluessel** unten ist, woran der Test eine Anfrage wiedererkennt: die",
        "volle URL samt Query. Zugeordnet wird nach der Anfrage und nicht nach der",
        "Reihenfolge — `srgssr_daily_briefing` ruft nebenlaeufig ab, und die Reihenfolge,",
        "in der die Antworten zurueckkommen, ist keine Zusicherung.",
        "",
        "Die Antworten stammen aus dem geteilten Client von `_http._get_http_client()`",
        "(gleicher User-Agent, gleiches Timeout, gleiche Retry-Mechanik wie im Betrieb),",
        "abgegriffen ueber einen httpx-Response-Hook. Ausgeloest hat sie jeweils das",
        "Werkzeug selbst — so belegt die Aufzeichnung auch, dass das Werkzeug genau",
        "diese Anfrage schickt.",
        "",
        "## Kein Token, keine Header",
        "",
        "Die Antwort von `/oauth/v1/accesstoken` traegt ein gueltiges Bearer-Token und",
        "wird nie abgelegt; ihre URL taucht auch als Schluessel nicht auf. Abgelegt sind",
        "ausschliesslich Antwort-Rumpfe — kein Header der Anfrage (dort steht",
        "`Authorization: Basic <key:secret>`) und keiner der Antwort. Vor dem Schreiben",
        "prueft der Recorder jede Datei und jeden Schluessel gegen Token, Key und Secret",
        "und bricht ab, statt zu warnen.",
        "",
        "## Auswahl",
        "",
        "Neu gesetzt ist die Einrueckung; gekuerzt ist allein die **Zahl** der",
        "Listeneintraege. Kein Feld eines behaltenen Eintrags ist angetastet, und",
        "Zaehlfelder daneben stehen wie geliefert.",
        "",
        "Wo der Server *in* einer Liste filtert, gruppiert oder zaehlt — Polis und das",
        "Tagesbriefing —, wird nicht gekuerzt: ein Schnitt erfaende dort einen",
        "Negativbefund, der wie ein Ergebnis aussieht.",
        "",
        "Die Fehlerpfade — Timeout, 5xx, 401, ein Gateway-Redirect — bleiben",
        "handgeschrieben. Sie lassen sich nicht auf Zuruf aufzeichnen und sind als",
        "Erfindung in Ordnung.",
        "",
    ]
    for a in antworten:
        zeilen += [
            f"## `{a.dateiname}`",
            "",
            f"- **Werkzeuge:** {', '.join(f'`{w}`' for w in sorted(a.werkzeuge))}",
            f"- **Schluessel:** `{a.schluessel}`",
        ]
        if a.notiz:
            zeilen.append(f"- **Notiz:** {a.notiz}")
        if a.gekuerzt_von > a.behalten:
            zeilen.append(
                f"- **Auswahl:** {a.behalten} von {a.gekuerzt_von} Listeneintraegen — "
                f"jede Liste im Baum auf die ersten {ZEILEN} gekuerzt, "
                f"aus {a.original_bytes} Bytes Rohantwort"
            )
        elif not a.darf_kuerzen:
            zeilen.append(
                "- **Auswahl:** ungekuerzt — der Server filtert oder zaehlt *in* dieser "
                "Liste, ein Schnitt erfaende einen Negativbefund"
            )
        else:
            zeilen.append("- **Auswahl:** ungekuerzt")
        zeilen += [
            f"- **Groesse:** {a.bytes} Bytes",
            f"- **SHA-256:** `{a.sha256}`",
            "",
        ]
    text = "\n".join(zeilen)
    _pruefe_kein_geheimnis(text, "PROVENANCE.md")
    (FIXTURES / "PROVENANCE.md").write_text(text, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
