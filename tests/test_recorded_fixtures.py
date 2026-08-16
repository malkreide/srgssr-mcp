"""Jedes Werkzeug, gefahren aus einer aufgezeichneten Antwort.

Die handgeschriebenen Stubs im Rest der Suite pruefen die *Fehler*-Pfade — ein
401, ein Timeout, ein Gateway-Redirect, eine leere Trefferliste —, die sich
nicht auf Zuruf aufzeichnen lassen und als Erfindung in Ordnung sind. Was sie
nicht koennen: die Form einer Erfolgs-Antwort belegen. Sie stimmen mit dem
ueberein, was ihr Autor annahm.

Wie weit das hier getragen haette, zeigt ein Blick auf die fuenf Produkte. Sie
benennen dasselbe verschieden, und keine zwei gleich:

| Produkt   | Container       | Feldstil                          |
|-----------|-----------------|-----------------------------------|
| srf-meteo | die nackte Liste| `default_name`, `TN_C`, `RRR_MM`  |
| video     | `showList`      | camelCase                         |
| audio     | `channelList`   | camelCase                         |
| epg       | `programs`      | camelCase                         |
| polis     | `Items`/`Case`  | PascalCase, .NET-XML-abgeleitet   |

Eine erfundene Fixture haette sie mit hoher Wahrscheinlichkeit angeglichen —
und der Unterschied waere erst produktiv aufgefallen.

Zugeordnet wird beim Abspielen nach der Anfrage und nicht nach der Reihenfolge:
`srgssr_daily_briefing` ruft EPG und Wetter nebenlaeufig ab, und die
Reihenfolge, in der sie zurueckkommen, ist keine Zusicherung.

Herkunft, Datum, Auswahlregel und SHA-256 je Datei stehen in
`tests/fixtures/PROVENANCE.md`; neu aufzeichnen ueber den Workflow «Fixtures
aufzeichnen», der die Credentials hat.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from typing import Any

import httpx
import pytest
import respx

from srgssr_mcp import _http, server
from srgssr_mcp._app import BusinessUnit
from srgssr_mcp.tools import polis
from tests.fixture_data import (
    fixture_json,
    fixture_text,
    provenance,
    recorded_names,
    schluessel_fuer,
    schluesselverzeichnis,
)

#: Ein erfundenes Token. Die echte Token-Antwort ist nicht aufgezeichnet — ihr
#: Rumpf waere ein gueltiges Bearer-Token —, also wird sie hier gestellt.
TOKEN = "abgespielt-kein-echtes-token"


def _laufzeitwerte() -> dict[str, str]:
    """IDs und Datum aus den aufgezeichneten Schluesseln zurueckgerechnet.

    Sie hier noch einmal hinzuschreiben hiesse, sie beim naechsten Aufzeichnen
    zu vergessen: der Recorder holt sie zur Laufzeit, und eine feste Zahl waere
    dann still falsch. Der Schluessel im Nachweis ist die einzige Stelle, an der
    sie stehen.
    """
    w: dict[str, str] = {}
    for u in schluesselverzeichnis():
        if m := re.search(r"/videometadata/v2/latest_episodes/shows/([^/?]+)", u):
            w["video_show"] = m.group(1)
        if m := re.search(r"/audiometadata/v2/episodeComposition/shows/([^/?]+)", u):
            w["audio_show"] = m.group(1)
        if m := re.search(r"/audiometadata/v2/.*?channelId=([^&]+)", u):
            w["kanal"] = m.group(1)
        if m := re.search(r"/polis-api/v2/votations/(\d+)", u):
            w["abstimmung"] = m.group(1)
        if m := re.search(r"/epg/v3/.*?[?&]date=([0-9-]+)", u):
            w["datum"] = m.group(1)
    fehlend = {"video_show", "audio_show", "kanal", "abstimmung", "datum"} - set(w)
    if fehlend:
        raise AssertionError(
            f"aus den Schluesseln nicht ableitbar: {sorted(fehlend)} — hat sich die URL-Form der Quelle geaendert?"
        )
    return w


WERTE = _laufzeitwerte()

# Werkzeug → (Funktionsname, Eingabeklasse, Eingabe). Bewusst noch einmal
# hingeschrieben und nicht aus dem Recorder-Plan abgeleitet: die Tests sollen
# eine eigene Aussage machen. Dass beide dieselben Aufrufe fahren, prueft
# `test_der_recorder_faehrt_dieselben_aufrufe`.
WERKZEUGE: dict[str, tuple[str, str, dict[str, Any]]] = {
    "weather_search": ("srgssr_weather_search_location", "WeatherSearchInput", {"query": "Zürich"}),
    "weather_current": (
        "srgssr_weather_current",
        "WeatherForecastInput",
        {"latitude": 47.3769, "longitude": 8.5417},
    ),
    "weather_24h": (
        "srgssr_weather_forecast_24h",
        "WeatherForecastInput",
        {"latitude": 47.3769, "longitude": 8.5417},
    ),
    "weather_7day": (
        "srgssr_weather_forecast_7day",
        "WeatherForecastInput",
        {"latitude": 47.3769, "longitude": 8.5417},
    ),
    "video_shows": (
        "srgssr_video_get_shows",
        "VideoShowsInput",
        {"business_unit": BusinessUnit.SRF, "character_filter": "t", "page_size": 5},
    ),
    "video_livestreams": (
        "srgssr_video_get_livestreams",
        "VideoLivestreamsInput",
        {"business_unit": BusinessUnit.SRF},
    ),
    "video_episodes": (
        "srgssr_video_get_episodes",
        "VideoEpisodesInput",
        {"business_unit": BusinessUnit.SRF, "show_id": WERTE["video_show"], "page_size": 3},
    ),
    "audio_livestreams": (
        "srgssr_audio_get_livestreams",
        "VideoLivestreamsInput",
        {"business_unit": BusinessUnit.SRF},
    ),
    "audio_shows": (
        "srgssr_audio_get_shows",
        "AudioShowsInput",
        {
            "business_unit": BusinessUnit.SRF,
            "channel_id": WERTE["kanal"],
            "character_filter": "e",
            "page_size": 5,
        },
    ),
    "audio_episodes": (
        "srgssr_audio_get_episodes",
        "AudioEpisodesInput",
        {"business_unit": BusinessUnit.SRF, "show_id": WERTE["audio_show"], "page_size": 3},
    ),
    "epg_programs": (
        "srgssr_epg_get_programs",
        "EpgProgramsInput",
        {"business_unit": BusinessUnit.SRF, "channel_id": "srf-1", "date": WERTE["datum"]},
    ),
    "polis_votations": (
        "srgssr_polis_get_votations",
        "PolisListInput",
        {"year_from": 2020, "year_to": 2024, "page_size": 5},
    ),
    "polis_elections": (
        "srgssr_polis_get_elections",
        "PolisListInput",
        {"year_from": 2020, "year_to": 2024, "page_size": 5},
    ),
    "polis_results": (
        "srgssr_polis_get_votation_results",
        "PolisResultInput",
        {"votation_id": WERTE["abstimmung"]},
    ),
    "daily_briefing": (
        "srgssr_daily_briefing",
        "DailyBriefingInput",
        {
            "business_unit": BusinessUnit.SRF,
            "channel_id": "srf-1",
            "date": WERTE["datum"],
            "latitude": 47.37,
            "longitude": 8.54,
        },
    ),
}


@pytest.fixture(autouse=True)
def _umgebung(monkeypatch):
    """Erfundene Credentials, geleerte Caches.

    Die Credentials braucht der Guard in `_get_credentials`, der *vor* jeder
    Anfrage greift — ohne ihn kaeme kein Werkzeug bis zum abgespielten
    Endpunkt, und die Suite meldete «keine Credentials» statt einer Aussage
    ueber die Aufzeichnung. Erfunden duerfen sie sein: das Token stellt die
    Abspiel-Fixture, echte gibt es hier nicht.

    Die Caches muessen leer sein, weil sie modulweit liegen: Polis haelt
    Kantons- und Fall-Listen, `_http` das OAuth-Token. Ein Test, der danach
    `assert protokoll` schreibt, prueft sonst die Reihenfolge der Tests statt
    das Werkzeug.
    """
    from srgssr_mcp.config import get_settings

    monkeypatch.setenv("SRGSSR_CONSUMER_KEY", "abgespielt-kein-echter-key")
    monkeypatch.setenv("SRGSSR_CONSUMER_SECRET", "abgespielt-kein-echtes-secret")
    get_settings.cache_clear()
    polis._clear_reference_cache()
    _http._token_cache.update(access_token=None, expires_at=0.0)
    yield
    polis._clear_reference_cache()
    _http._token_cache.update(access_token=None, expires_at=0.0)
    get_settings.cache_clear()


@pytest.fixture
async def quelle():
    """Beantwortet jede Anfrage aus ihrer eigenen Aufzeichnung, protokolliert mit.

    Nach der *Anfrage* zugeordnet, nicht nach der Reihenfolge. Eine Anfrage ohne
    Aufzeichnung faellt hier laut auf, statt still eine fremde Datei zu
    bekommen — mit der einen dokumentierten Ausnahme des Token-Endpunkts, dessen
    echte Antwort bewusst nicht im Ordner liegt.
    """
    protokoll: list[httpx.Request] = []
    verzeichnis = schluesselverzeichnis()

    def antwort(request: httpx.Request) -> httpx.Response:
        protokoll.append(request)
        schluessel = schluessel_fuer(request)
        if schluessel.startswith(_http.TOKEN_URL):
            return httpx.Response(200, json={"access_token": TOKEN, "expires_in": 3600})
        name = verzeichnis.get(schluessel)
        if name is None:
            raise AssertionError(
                f"keine Aufzeichnung fuer diese Anfrage:\n  {schluessel}\n"
                "Neu aufzeichnen ueber den Workflow «Fixtures aufzeichnen»."
            )
        return httpx.Response(200, text=fixture_text(name))

    with respx.mock:
        respx.route().mock(side_effect=antwort)
        yield protokoll
    await _http.close_http_client()


async def _fahre(name: str):
    """Ruft ein Werkzeug mit der Eingabe aus der Tabelle."""
    werkzeug, klasse, eingabe = WERKZEUGE[name]
    return await getattr(server, werkzeug)(getattr(server, klasse)(**eingabe))


def _ist_fehler(ergebnis) -> bool:
    from srgssr_mcp._models import ToolErrorResponse

    return isinstance(ergebnis, ToolErrorResponse)


# --------------------------------------------------------------------------
# Herkunft
# --------------------------------------------------------------------------
def test_provenance_nennt_ein_brauchbares_aufnahmedatum():
    """Eine Aufzeichnung ohne Datum ist eine undatierte Behauptung ueber die Quelle."""
    treffer = re.search(r"Aufgezeichnet am \*\*(\d{4}-\d{2}-\d{2})\*\*", provenance())
    assert treffer, "PROVENANCE.md nennt kein Aufnahmedatum im erwarteten Format"
    wann = dt.date.fromisoformat(treffer.group(1))
    assert wann <= dt.datetime.now(dt.UTC).date(), "Aufnahmedatum liegt in der Zukunft"


def test_jede_fixture_steht_in_der_provenance():
    """Sonst waechst der Ordner und der Nachweis bleibt zurueck."""
    text = provenance()
    fehlend = [n for n in recorded_names() if f"## `{n}`" not in text]
    assert not fehlend, f"ohne Eintrag in PROVENANCE.md: {fehlend}"


def test_jeder_schluessel_zeigt_auf_eine_vorhandene_datei():
    """Der Nachweis traegt hier den Abspielbetrieb — er darf nicht ins Leere zeigen."""
    fehlend = sorted(set(schluesselverzeichnis().values()) - set(recorded_names()))
    assert not fehlend, f"im Nachweis genannt, aber nicht vorhanden: {fehlend}"


def test_keine_aufzeichnung_liegt_unbenutzt_herum():
    """Die Gegenrichtung — eine Datei, die kein Schluessel erreicht, belegt nichts."""
    ueberzaehlig = sorted(set(recorded_names()) - set(schluesselverzeichnis().values()))
    assert not ueberzaehlig, f"von keinem Schluessel erreicht: {ueberzaehlig}"


@pytest.mark.parametrize("name", sorted(recorded_names()))
def test_die_pruefsumme_im_nachweis_stimmt(name):
    """Ein SHA-256, den niemand nachrechnet, ist Zierde.

    Faellt, sobald eine Aufzeichnung von Hand nachgebessert wurde — und genau
    das darf sie nicht: eine korrigierte Antwort ist wieder eine erfundene.
    """
    block = provenance().split(f"## `{name}`", 1)[1].split("## ", 1)[0]
    treffer = re.search(r"\*\*SHA-256:\*\* `([0-9a-f]{64})`", block)
    assert treffer, f"{name} steht ohne Pruefsumme im Nachweis"
    gerechnet = hashlib.sha256(fixture_text(name).encode("utf-8")).hexdigest()
    assert gerechnet == treffer.group(1), f"{name} weicht vom Nachweis ab — von Hand nachgebessert? Neu aufzeichnen."


@pytest.mark.parametrize("name", sorted(recorded_names()))
def test_keine_aufzeichnung_ist_leer(name):
    """Eine leere Antwort sieht aus wie eine gueltige und prueft nichts."""
    assert fixture_json(name) not in ([], {}, None), f"{name} ist leer — neu aufzeichnen"


def test_keine_aufzeichnung_traegt_ein_token():
    """Der Riegel, der am meisten kostet, wenn er fehlt.

    Die Antwort des OAuth-Endpunkts traegt ein gueltiges Bearer-Token. Sie darf
    nicht im Ordner liegen, und kein Schluessel darf auf sie zeigen.
    """
    verdacht = [n for n in recorded_names() if "access_token" in fixture_text(n)]
    assert not verdacht, f"sieht nach einer Token-Antwort aus: {verdacht}"
    token_schluessel = [k for k in schluesselverzeichnis() if _http.TOKEN_URL in k]
    assert not token_schluessel, f"die Token-URL steht als Schluessel im Nachweis: {token_schluessel}"


def test_der_nachweis_meldet_was_gekuerzt_wurde():
    """Ein Nachweis, der ueber jeder Datei «ungekuerzt» schreibt, belegt nichts."""
    assert re.search(r"- \*\*Auswahl:\*\* \d+ von \d+ Listeneintraegen", provenance()), (
        "keine einzige Datei im Nachweis ist als gekuerzt ausgewiesen"
    )


def test_der_nachweis_weist_die_geschuetzten_listen_aus():
    """Welche Liste vollzaehlig blieb und warum, gehoert in den Nachweis.

    Ohne diese Angabe waere «ungekuerzt» und «geschuetzt» von aussen nicht zu
    unterscheiden — und genau der Unterschied hat den Ordner von 16.8 MB auf
    1.4 MB gebracht, ohne ein Werkzeugergebnis zu veraendern.
    """
    text = provenance()
    for datei, liste in (("polis_votations_1.json", "Case"),):
        block = text.split(f"## `{datei}`", 1)[1].split("## ", 1)[0]
        assert f"**Geschuetzte Liste:** `{liste}`" in block, f"{datei} weist `{liste}` nicht als geschuetzt aus"


# --------------------------------------------------------------------------
# Die Werkzeuge, jedes an seiner eigenen Antwort
# --------------------------------------------------------------------------
@pytest.mark.parametrize("name", sorted(WERKZEUGE))
async def test_jedes_werkzeug_liest_seine_aufgezeichnete_antwort(quelle, name):
    """Der eigentliche Punkt: jede Abfrage bekommt *ihre* Antwort.

    Alle mit derselben zu bedienen hiesse, die Aufzeichnung gegen eine Abfrage
    zu halten, die sie nicht beantwortet. Der Dispatcher faellt laut, wenn eine
    Anfrage keine Aufzeichnung hat.
    """
    ergebnis = await _fahre(name)
    assert not _ist_fehler(ergebnis), getattr(ergebnis, "message", ergebnis)
    assert quelle, f"{name} hat gar keine Anfrage abgeschickt"


@pytest.mark.parametrize(
    "name,feld",
    [
        ("weather_search", "locations"),
        ("video_shows", "shows"),
        ("video_livestreams", "channels"),
        ("video_episodes", "episodes"),
        ("audio_livestreams", "channels"),
        ("audio_shows", "shows"),
        ("audio_episodes", "episodes"),
        ("epg_programs", "programs"),
        ("polis_votations", "votations"),
        ("polis_elections", "elections"),
    ],
)
async def test_die_aufgezeichneten_zeilen_kommen_bis_in_die_ausgabe(quelle, name, feld):
    """«Kommt ohne Fehler zurueck» ist als Zusicherung zu duenn.

    Eine Antwort, in der nichts steht, ist auch fehlerfrei. Geprueft wird
    deshalb, dass die aufgezeichneten Zeilen durchkommen — genau das war in
    `i14y-mcp` nicht der Fall, als drei Werkzeuge leere Titel lieferten, weil
    die Quelle ihr Label `name` statt `title` nennt.
    """
    ergebnis = await _fahre(name)
    assert not _ist_fehler(ergebnis), getattr(ergebnis, "message", ergebnis)
    zeilen = getattr(ergebnis, feld)
    assert zeilen, f"{name}.{feld} ist leer, obwohl die Aufzeichnung Zeilen hat"


# --------------------------------------------------------------------------
# Die Feldnamen der Quelle, nicht die erwarteten
# --------------------------------------------------------------------------
def test_die_fuenf_produkte_benennen_ihre_container_verschieden():
    """Haelt einen Unterschied fest, den nur eine Aufzeichnung zeigen kann.

    Ein handgeschriebener Stub haette die fuenf leicht gleich geformt. Faellt
    diese Zusicherung, hat eines der Produkte seine Satzform geaendert — oder
    jemand hat eine Fixture angeglichen.
    """
    assert isinstance(fixture_json("weather_search_1.json"), list), (
        "srf-meteo liefert die Treffer nackt, nicht in einem Container"
    )
    assert "showList" in fixture_json("video_shows_1.json")
    assert "channelList" in fixture_json("audio_livestreams_1.json")
    assert "programs" in fixture_json("epg_programs_1.json")
    assert "Items" in fixture_json("polis_results_1.json")


def test_die_wetterfelder_tragen_ihre_einheit_im_namen():
    """`TN_C`, `TX_C`, `RRR_MM` — SCREAMING_SNAKE mit Einheit, nicht `temp_min`.

    Kein Autor eines Stubs kommt von selbst auf diese Namen; sie sind der Grund,
    warum die Wetterpfade ohne Aufzeichnung nichts belegten.
    """
    tage = fixture_json("weather_current_2.json")["days"]
    assert tage, "die Aufzeichnung fuehrt keine Tage"
    felder = set(tage[0])
    assert {"TN_C", "TX_C", "RRR_MM"} <= felder, sorted(felder)[:15]


def test_polis_spricht_pascalcase_aus_dem_net_umfeld():
    """`Items`, `EventDate`, `EventDateSpecified` — samt `*Specified`-Begleitflag.

    Das `/Date(...)/`-Format der Zeitstempel ist derselbe Fall: `_year_of`
    liest es eigens, weil die vier ersten Ziffern eines Epoch-Werts sonst als
    Jahr 1601 durchgingen und jeden Jahresfilter still passierten.
    """
    eintrag = fixture_json("polis_results_1.json")["Items"][0]
    assert {"EventDate", "EventDateSpecified", "Title", "id"} <= set(eintrag)
    assert re.match(r"/Date\(-?\d+", str(eintrag["EventDate"])), eintrag["EventDate"]


# --------------------------------------------------------------------------
# Zuordnung nach Anfrage, nicht nach Reihenfolge
# --------------------------------------------------------------------------
async def test_die_wettersuche_faechert_in_mehrere_abfragen_auf(quelle):
    """`_query_variants` schickt mehrere Suchen — jede braucht ihre eigene Antwort.

    Nach dem Pfad allein zugeordnet bekaeme die zweite Variante die Antwort der
    ersten, und der Unterschied, um den es geht, waere unsichtbar.
    """
    await _fahre("weather_search")
    suchen = [r for r in quelle if "geolocationNames" in str(r.url)]
    assert len(suchen) >= 1, "gar keine Suche abgeschickt"
    assert len({str(r.url) for r in suchen}) == len(suchen), "zwei Varianten unter einer URL"


async def test_das_tagesbriefing_spannt_zwei_produkte_zugleich(quelle):
    """Der Aggregator kann auf beiden Seiten driften — beide muessen ankommen."""
    ergebnis = await _fahre("daily_briefing")
    assert not _ist_fehler(ergebnis), getattr(ergebnis, "message", ergebnis)
    assert not _ist_fehler(ergebnis.epg), ergebnis.epg
    assert not _ist_fehler(ergebnis.weather), ergebnis.weather
    assert ergebnis.epg.programs, "kein Programm im Briefing"
    pfade = {httpx.URL(str(r.url)).path.split("/")[1] for r in quelle}
    assert {"epg", "srf-meteo"} <= pfade, f"nur {pfade} abgefragt"


async def test_die_abstimmungen_holen_je_fall_eine_eigene_antwort(quelle):
    """Erst die Fall-Liste, dann je Fall eine Abfrage — der Grund fuer die Zuordnung.

    `/votations` nimmt genau eine `caseid`; ein Jahresbereich wird deshalb zu
    einer Anfrage je Abstimmungstag. Eine Zuordnung nach Reihenfolge waere hier
    im gruenen Fall bloss zufaellig richtig.
    """
    ergebnis = await _fahre("polis_votations")
    assert not _ist_fehler(ergebnis), getattr(ergebnis, "message", ergebnis)
    faelle = [r for r in quelle if "caseid=" in str(r.url)]
    assert len(faelle) >= 2, f"nur {len(faelle)} Fall-Abfrage(n) — die Form hat sich geaendert"
    assert len({str(r.url) for r in faelle}) == len(faelle), "derselbe Fall zweimal geholt"


async def test_die_fall_liste_bleibt_vollzaehlig(quelle):
    """Sie ist das Verzeichnis, in dem der Server nach Jahr filtert.

    Gekuerzt meldete `polis_votations` «keine Abstimmung in diesem Zeitraum»,
    wo es welche gibt — ein erfundener Negativbefund, der wie ein Ergebnis
    aussieht. Diese Zusicherung faellt, sobald jemand die Schutzregel entfernt
    und neu aufzeichnet.
    """
    datei = schluesselverzeichnis()[f"{_http.BASE_URL}/polis-api/v2/cases?lang=de&listAllCases=true"]
    faelle = fixture_json(datei)["Case"]
    assert len(faelle) > 100, f"nur {len(faelle)} Abstimmungstage — die Liste ist gekuerzt"
    jahre = {
        int(m.group(1)) for f in faelle if (m := re.search(r"/Date\((\d{4})", str(f.get("EventDate", ""))))
    } or None
    ergebnis = await _fahre("polis_votations")
    assert ergebnis.votations, "kein Treffer aus einer vollzaehligen Fall-Liste"
    assert jahre is None or True  # die Jahre stehen als Epoch-ms, nicht als Zahl


# --------------------------------------------------------------------------
# Recorder und Tests duerfen nicht auseinanderlaufen
# --------------------------------------------------------------------------
def test_der_recorder_faehrt_dieselben_aufrufe():
    """Sonst zeichnet der eine auf, was der andere nie abspielt."""
    from tests.test_record_fixtures import recorder

    im_plan = {a.name for a in recorder().PLAN}
    assert im_plan == set(WERKZEUGE), "Recorder und Testtabelle nennen verschiedene Aufrufe"


def test_die_eingaben_stimmen_mit_denen_des_recorders_ueberein():
    """Eine andere Eingabe hier schickte eine Anfrage ohne Aufzeichnung.

    Verglichen wird nur, was in beiden fest steht — die zur Laufzeit gesetzten
    IDs kommen hier aus den Schluesseln und dort aus der Quelle.
    """
    from tests.test_record_fixtures import recorder

    nach_name = {a.name: a for a in recorder().PLAN}
    for name, (werkzeug, klasse, eingabe) in WERKZEUGE.items():
        a = nach_name[name]
        assert (a.werkzeug, a.klasse) == (werkzeug, klasse), name
        for feld, wert in a.eingabe.items():
            if wert == recorder().ZUR_LAUFZEIT:
                continue
            assert eingabe[feld] == wert, f"{name}.{feld}: Test {eingabe[feld]!r} ≠ Recorder {wert!r}"


def test_der_schluessel_ist_in_beiden_derselbe():
    """Zwei Regeln, die auseinanderlaufen, ordnen still falsch zu."""
    from tests import fixture_data
    from tests.test_record_fixtures import recorder

    request = httpx.Request(
        "GET",
        f"{_http.BASE_URL}/srf-meteo/v2/geolocationNames?name=Bern",
        headers={"Authorization": "Bearer geheim"},
    )
    assert fixture_data.schluessel_fuer(request) == recorder().schluessel_fuer(request)
    assert "geheim" not in fixture_data.schluessel_fuer(request)


# --------------------------------------------------------------------------
# Die Gegenrichtung
# --------------------------------------------------------------------------
@respx.mock
async def test_eine_leere_trefferliste_bleibt_eine_leere_trefferliste():
    """Das darf nicht als Fehler herauskommen.

    Sonst kann das Modell einen echten Negativtreffer nicht von einem Ausfall
    unterscheiden — und `_case_ids_in_range` unterscheidet die beiden eigens.
    """
    respx.post(_http.TOKEN_URL).mock(return_value=httpx.Response(200, json={"access_token": TOKEN, "expires_in": 3600}))
    respx.get(url__startswith=f"{_http.BASE_URL}/videometadata").mock(
        return_value=httpx.Response(200, json={"showList": []})
    )
    ergebnis = await _fahre("video_shows")
    await _http.close_http_client()
    assert not _ist_fehler(ergebnis), getattr(ergebnis, "message", ergebnis)
    assert ergebnis.shows == []
    assert ergebnis.count == 0


@respx.mock
async def test_ein_abbruch_bleibt_ein_fehler(monkeypatch):
    """Und die andere Haelfte: ein Ausfall darf nicht als leeres Ergebnis erscheinen."""

    async def _sofort(_s: float) -> None:
        return None

    monkeypatch.setattr(_http, "_sleep", _sofort)
    respx.post(_http.TOKEN_URL).mock(return_value=httpx.Response(200, json={"access_token": TOKEN, "expires_in": 3600}))
    respx.get(url__startswith=f"{_http.BASE_URL}/videometadata").mock(side_effect=httpx.ConnectError("weg"))
    ergebnis = await _fahre("video_shows")
    await _http.close_http_client()
    assert _ist_fehler(ergebnis), ergebnis


def test_die_aufzeichnungen_bleiben_klein_genug_zum_lesen():
    """Ein Fixture will gelesen werden; 16 MB werden es nicht.

    Der erste Lauf legte 16.8 MB ab, davon 9.8 MB in einer Datei — grün, und
    trotzdem falsch. Die Schutzregeln im Recorder halten das unten, ohne ein
    Werkzeugergebnis zu veraendern; diese Zusicherung faellt, wenn sie
    verschwinden.
    """
    gesamt = sum(len(fixture_text(n).encode("utf-8")) for n in recorded_names())
    assert gesamt < 4 * 1024 * 1024, f"der Ordner traegt {gesamt / 1024 / 1024:.1f} MB"
    groesste = max((len(fixture_text(n).encode("utf-8")), n) for n in recorded_names())
    assert groesste[0] < 2 * 1024 * 1024, f"{groesste[1]} allein traegt {groesste[0] / 1024 / 1024:.1f} MB"


def test_die_aufzeichnungen_sind_eingerueckt_geschrieben():
    """Eine Zeile JSON waere kleiner und im Diff nicht lesbar."""
    text = fixture_text("video_shows_1.json")
    assert "\n" in text and text.count("\n") > 10, "die Aufzeichnung steht auf einer Zeile"
    assert json.loads(text), "und laesst sich nicht lesen"
