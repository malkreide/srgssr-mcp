"""Der Recorder selbst, gefahren gegen eine gemockte API.

Die Aufzeichnungen fehlen noch: sie brauchen `SRGSSR_CONSUMER_KEY` und
`SRGSSR_CONSUMER_SECRET`, und diese Umgebung hat keine. `api.srgssr.ch` ist von
hier aus erreichbar und antwortet mit HTTP 401 — es fehlen allein die
Credentials, nicht der Zugang. Aufgezeichnet wird deshalb dort, wo sie schon
liegen: `.github/workflows/record-fixtures.yml` faehrt denselben Befehl mit
denselben Secrets wie die naechtliche Live-Suite.

Was dieser Test leistet, ist die andere Haelfte davon. Ein Recorder, den
niemand fahren kann und den auch niemand prueft, waere genau das plausibel
aussehende, unwiderlegbare Artefakt, gegen das die ganze Fixture-Konvention
gerichtet ist. Seine **Mechanik** haengt aber nicht an den Credentials: Plan,
Zuordnung, Kuerzung, Nachweis und — der Kern hier — der Umgang mit dem
OAuth-Token lassen sich mit einem erfundenen Token gegen eine gemockte API
vollstaendig pruefen.

Der Token-Teil ist kein Formalismus. Diese API ist die einzige im Portfolio mit
OAuth2: die Antwort von `/oauth/v1/accesstoken` traegt ein gueltiges
Bearer-Token, und die Anfrage dorthin `Authorization: Basic <key:secret>`. Ein
Recorder, der «jede Antwort» ablegt, committet beim ersten Lauf ein
funktionierendes Token in ein oeffentliches Repository.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path

import httpx
import pytest
import respx

from srgssr_mcp import _http, server
from srgssr_mcp._app import BusinessUnit

WURZEL = Path(__file__).resolve().parent.parent
RECORDER_PFAD = WURZEL / "scripts" / "record_fixtures.py"

# Erfundene Geheimnisse — sie stehen hier, damit die Tests unten *pruefen*
# koennen, dass keines davon in einer Datei landet. Echte gibt es in dieser
# Umgebung nicht, und der Test braucht auch keine.
KEY = "test-consumer-key-aaaa"
SECRET = "test-consumer-secret-bbbb"
TOKEN = "test-access-token-cccc-dddd-eeee"


def recorder():
    """Laedt `scripts/record_fixtures.py` als Modul, ohne `main()` zu rufen.

    In `sys.modules` eingetragen *vor* `exec_module`: das Skript importiert
    beim Laden `srgssr_mcp`, und ein halb geladenes Modul im Zwischenzustand
    liefert sonst schwer lesbare Fehler.
    """
    if "srgssr_recorder" in sys.modules:
        return sys.modules["srgssr_recorder"]
    spec = importlib.util.spec_from_file_location("srgssr_recorder", RECORDER_PFAD)
    assert spec and spec.loader
    modul = importlib.util.module_from_spec(spec)
    sys.modules["srgssr_recorder"] = modul
    spec.loader.exec_module(modul)
    return modul


@pytest.fixture(autouse=True)
def _credentials(monkeypatch):
    """Erfundene Credentials und ein geleerter Token-Cache je Test."""
    monkeypatch.setenv("SRGSSR_CONSUMER_KEY", KEY)
    monkeypatch.setenv("SRGSSR_CONSUMER_SECRET", SECRET)
    from srgssr_mcp.config import get_settings

    get_settings.cache_clear()
    _http._token_cache["access_token"] = None
    _http._token_cache["expires_at"] = 0.0
    yield
    _http._token_cache["access_token"] = None
    _http._token_cache["expires_at"] = 0.0
    get_settings.cache_clear()


@pytest.fixture
async def geschlossener_client():
    """Der geteilte Client ist prozessweit — nach dem Test zumachen."""
    yield
    await _http.close_http_client()


def mocke_token() -> respx.Route:
    """Das Token-Endpunkt, mit einer Antwort in der Form der echten."""
    return respx.post(_http.TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": TOKEN, "expires_in": 3600})
    )


# --------------------------------------------------------------------------
# Das Token
# --------------------------------------------------------------------------


@respx.mock
async def test_die_token_antwort_wird_nie_aufgezeichnet(geschlossener_client):
    """Der Kern. Ihr Rumpf ist ein gueltiges Bearer-Token.

    Gefahren wird ein echter Werkzeugaufruf durch `_fahre`, damit der
    Token-Refresh wirklich stattfindet — auf die Konstante `NIE_AUFZEICHNEN` zu
    schauen belegte nur, dass jemand sie hingeschrieben hat.
    """
    m = recorder()
    mocke_token()
    respx.get(url__startswith=f"{_http.BASE_URL}/srf-meteo").mock(
        return_value=httpx.Response(200, json={"geolocations": []})
    )

    antworten = await m._fahre(
        m.Aufruf("wetter", "srgssr_weather_search_location", "WeatherSearchInput", {"query": "Bern"})
    )

    assert antworten, "gar keine Antwort gesehen — der Aufruf lief nicht"
    for a in antworten:
        assert _http.TOKEN_URL not in a.schluessel, "die Token-URL ist ein Schluessel geworden"
        assert TOKEN not in a.text, "eine Aufzeichnung traegt das Bearer-Token"


@respx.mock
async def test_der_token_refresh_ist_ueberhaupt_gelaufen(geschlossener_client):
    """Sonst belegte der Test darueber nichts.

    Wuerde der Token-Refresh gar nicht stattfinden — etwa weil ein Cache ihn
    ueberspringt —, dann waere «kein Token in den Aufzeichnungen» wahr und
    bedeutungslos. Diese Zusicherung haelt fest, dass die Antwort, die *nicht*
    abgelegt werden darf, tatsaechlich durch den Hook gelaufen ist.
    """
    m = recorder()
    token_route = mocke_token()
    respx.get(url__startswith=f"{_http.BASE_URL}/srf-meteo").mock(
        return_value=httpx.Response(200, json={"geolocations": []})
    )

    await m._fahre(m.Aufruf("wetter", "srgssr_weather_search_location", "WeatherSearchInput", {"query": "Bern"}))

    assert token_route.called, "kein Token-Refresh — der Ausschluss oben prueft nichts"


def test_der_ausschluss_trifft_die_token_url():
    """Die Regel selbst, direkt: was `NIE_AUFZEICHNEN` sagt, muss auch greifen."""
    m = recorder()
    assert m._ist_gesperrt(_http.TOKEN_URL)
    assert m._ist_gesperrt(f"{_http.TOKEN_URL}?grant_type=client_credentials")
    assert not m._ist_gesperrt(f"{_http.BASE_URL}/srf-meteo/v2/geolocationNames?name=Bern")


def test_der_schluessel_nimmt_keinen_header_mit():
    """Die Anfrage ans Token-Endpunkt traegt `Authorization: Basic <key:secret>`.

    Ein Schluessel, der Header mitnaehme, schriebe das Geheimnis in
    `PROVENANCE.md` — eine Datei, die ausdruecklich zum Lesen gedacht ist.
    """
    m = recorder()
    request = httpx.Request(
        "GET",
        f"{_http.BASE_URL}/srf-meteo/v2/geolocationNames?name=Bern",
        headers={"Authorization": f"Bearer {TOKEN}", "X-Key": SECRET},
    )
    schluessel = m.schluessel_fuer(request)
    assert TOKEN not in schluessel
    assert SECRET not in schluessel
    assert "geolocationNames" in schluessel and "name=Bern" in schluessel


def test_die_geheimnis_pruefung_bricht_ab_statt_zu_warnen(monkeypatch):
    """Eine Warnung wuerde im Log untergehen und die Datei traegt trotzdem das Token.

    Geprueft wird auch die Gegenrichtung: harmloser Text darf durchgehen, sonst
    waere die Pruefung ein Totalausfall statt eines Wachhundes.
    """
    m = recorder()
    _http._token_cache["access_token"] = TOKEN

    with pytest.raises(SystemExit) as abbruch:
        m._pruefe_kein_geheimnis(f'{{"a": "{TOKEN}"}}', "irgendeine.json")
    assert "ABBRUCH" in str(abbruch.value)

    with pytest.raises(SystemExit):
        m._pruefe_kein_geheimnis(f"...{SECRET}...", "irgendeine.json")

    m._pruefe_kein_geheimnis('{"title": "Tagesschau"}', "harmlos.json")


def test_ein_leeres_geheimnis_macht_die_pruefung_nicht_trivial(monkeypatch):
    """Ohne diesen Filter waere `"" in text` immer wahr — und jede Datei ein Abbruch.

    Der Fehler waere laut und schnell gefunden. Der umgekehrte, den diese
    Zusicherung mit abdeckt, waere es nicht: `_geheimnisse()` darf den leeren
    String nicht fuehren, sonst prueft sie ihn statt der echten Werte.
    """
    m = recorder()
    monkeypatch.delenv("SRGSSR_CONSUMER_KEY", raising=False)
    monkeypatch.delenv("SRGSSR_CONSUMER_SECRET", raising=False)
    _http._token_cache["access_token"] = None
    assert m._geheimnisse() == []
    m._pruefe_kein_geheimnis("beliebiger Text", "harmlos.json")


# --------------------------------------------------------------------------
# Plan und Zuordnung
# --------------------------------------------------------------------------


def test_der_plan_nennt_jedes_werkzeug_des_servers():
    """Ein neues Werkzeug ohne Plan-Eintrag bliebe sonst still ohne Aufzeichnung."""
    m = recorder()
    im_plan = {a.werkzeug for a in m.PLAN}
    am_server = {n for n in dir(server) if n.startswith("srgssr_") and callable(getattr(server, n))}
    fehlend = sorted(am_server - im_plan)
    assert not fehlend, f"Werkzeuge ohne Plan-Eintrag: {fehlend}"
    unbekannt = sorted(im_plan - am_server)
    assert not unbekannt, f"Plan nennt Werkzeuge, die es nicht gibt: {unbekannt}"


def test_jede_plan_eingabe_baut_ein_gueltiges_modell():
    """Ein Tippfehler faellt hier und nicht erst nach dem Token-Refresh.

    Die Platzhalter werden vorher gesetzt — genau so, wie `main()` es tut.
    Diese Zusicherung fand beim Schreiben neun ungueltige Eingaben auf einmal:
    `business_unit` will die Enum, nicht den String.
    """
    m = recorder()
    werte = {
        "video_episodes": {"show_id": "x"},
        "audio_shows": {"channel_id": "x"},
        "audio_episodes": {"show_id": "x"},
        "polis_results": {"votation_id": "x"},
        "epg_programs": {"date": "2026-08-15"},
        "daily_briefing": {"date": "2026-08-15"},
    }
    for a in m._mit_laufzeitwerten(m.PLAN, werte):
        getattr(server, a.klasse)(**a.eingabe)  # wirft bei ungueltiger Eingabe


def test_ein_uebriggebliebener_platzhalter_faellt_auf():
    """Sonst meldete erst die Modell-Validierung «String too short».

    Das ist wahr und sagt nichts darueber, dass eine ID nicht besorgt wurde.
    """
    m = recorder()
    with pytest.raises(RuntimeError) as fehler:
        m._mit_laufzeitwerten(m.PLAN, {})
    assert m.ZUR_LAUFZEIT in str(fehler.value)


def test_die_plan_eingaben_stammen_aus_der_live_suite():
    """Erfundene Eingaben waeren wieder eine Annahme des Autors.

    Die Live-Suite faehrt ihre naechtlich gegen die echte API — dass sie Treffer
    liefern, ist damit belegt und nicht behauptet. Geprueft wird an den Werten,
    die beide gemeinsam haben.
    """
    m = recorder()
    live = (WURZEL / "tests" / "test_live.py").read_text(encoding="utf-8")
    nach_name = {a.name: a for a in m.PLAN}
    assert 'character_filter="t"' in live
    assert nach_name["video_shows"].eingabe["character_filter"] == "t"
    assert "year_from=2020, year_to=2024" in live
    assert nach_name["polis_votations"].eingabe["year_from"] == 2020
    assert 'channel_id="srf-1"' in live
    assert nach_name["epg_programs"].eingabe["channel_id"] == "srf-1"


@respx.mock
async def test_zugeordnet_wird_nach_der_anfrage_nicht_nach_der_reihenfolge(geschlossener_client):
    """Zwei Abfragen an denselben Pfad muessen zwei Schluessel ergeben.

    `srgssr_weather_search_location` faechert ueber `_query_variants` auf. Nach
    dem Pfad allein zugeordnet, waeren die Varianten nicht auseinanderzuhalten —
    und beim Abspielen bekaeme die eine still die Antwort der anderen.
    """
    m = recorder()
    mocke_token()
    gesehen: list[str] = []

    def antwort(request: httpx.Request) -> httpx.Response:
        gesehen.append(str(request.url))
        # Leer, damit die Fuzzy-Wiederholung alle Varianten durchprobiert.
        return httpx.Response(200, json={"geolocations": []})

    respx.get(url__startswith=f"{_http.BASE_URL}/srf-meteo").mock(side_effect=antwort)

    antworten = await m._fahre(
        m.Aufruf("wetter", "srgssr_weather_search_location", "WeatherSearchInput", {"query": "Zürich"})
    )

    assert len(gesehen) > 1, "nur eine Variante abgefragt — der Faecher ist weg"
    assert len(set(gesehen)) == len(gesehen), "zwei Varianten unter derselben URL"
    schluessel = [a.schluessel for a in antworten]
    assert len(set(schluessel)) == len(schluessel), (
        "zwei Antworten unter demselben Schluessel — beim Abspielen bekaeme eine Abfrage die Antwort einer anderen"
    )
    assert all("srf-meteo" in s for s in schluessel)


@respx.mock
async def test_eine_fehlerantwort_wird_nicht_aufgezeichnet(geschlossener_client):
    """Ein 500 als Fixture gaebe sich als das aus, was die Quelle normalerweise sagt."""
    m = recorder()
    mocke_token()
    respx.get(url__startswith=f"{_http.BASE_URL}/srf-meteo").mock(
        return_value=httpx.Response(500, json={"error": "kaputt"})
    )

    gesehen: list = []
    hook = m._hook_fuer(gesehen)
    client = await _http._get_http_client()
    request = httpx.Request("GET", f"{_http.BASE_URL}/srf-meteo/v2/geolocationNames?name=Bern")
    await hook(httpx.Response(500, json={"error": "kaputt"}, request=request))
    assert gesehen == [], "eine Fehlerantwort ist in den Ordner geraten"
    assert client is not None


# --------------------------------------------------------------------------
# Kuerzen und Nachweis
# --------------------------------------------------------------------------


def test_kuerzen_meldet_seine_zaehler_nach_dem_lauf():
    """`return vorher, nachher, geh(daten)` liest die Zahlen, *bevor* `geh` sie hochzaehlt.

    Der Nachweis schriebe dann «ungekuerzt» ueber jede gekuerzte Datei — in vier
    Repos des Portfolios ist genau das passiert.
    """
    m = recorder()
    vorher, nachher, gekuerzt = m._kuerze({"a": list(range(m.ZEILEN * 3))})
    assert (vorher, nachher) == (m.ZEILEN * 3, m.ZEILEN)
    assert len(gekuerzt["a"]) == m.ZEILEN


def test_kuerzen_ruehrt_kein_feld_an():
    """Nur die Zahl der Eintraege. Ein Zaehlfeld daneben meint die Gesamtzahl."""
    m = recorder()
    roh = {
        "total": 4711,
        "shows": [{"id": str(i), "title": f"t{i}", "description": "d"} for i in range(10)],
    }
    _, _, gekuerzt = m._kuerze(json.loads(json.dumps(roh)))
    assert gekuerzt["total"] == 4711, "ein Zaehlfeld wurde mitgekuerzt"
    assert len(gekuerzt["shows"]) == m.ZEILEN
    assert set(gekuerzt["shows"][0]) == {"id", "title", "description"}, "ein Feld fehlt"


def test_die_geschuetzte_liste_behaelt_alle_eintraege():
    """Der Schutz gilt der Laenge, nicht dem Inhalt.

    Die geschuetzte Liste behaelt jeden Eintrag — der Server zaehlt sie —, aber
    was *unter* den Eintraegen haengt, wird normal gekuerzt. Genau dort sitzt
    bei Polis das Gewicht: die Fall-Liste ist schmal, die Ergebnisbaeume
    darunter sind es nicht.
    """
    m = recorder()
    roh = {
        "Case": [{"id": i, "Votations": {"Votation": list(range(10))}} for i in range(20)],
        "Anderes": list(range(20)),
    }
    schutz = m.schutz_fuer("https://api.srgssr.ch/polis-api/v2/cases?lang=de")
    assert schutz is not None and schutz.schluessel == "Case"
    _, _, gekuerzt = m._kuerze(json.loads(json.dumps(roh)), schutz)
    assert len(gekuerzt["Case"]) == 20, "die geschuetzte Liste wurde gekuerzt"
    assert len(gekuerzt["Case"][0]["Votations"]["Votation"]) == m.ZEILEN, (
        "unter der geschuetzten Liste wurde nicht gekuerzt — dort sitzt das Gewicht"
    )
    assert len(gekuerzt["Anderes"]) == m.ZEILEN, "eine ungeschuetzte Liste blieb voll"


def test_ohne_schutzregel_wird_alles_gekuerzt():
    """Die Gegenrichtung: sonst waere der Schutz nicht von «immer voll» zu trennen."""
    m = recorder()
    assert m.schutz_fuer("https://api.srgssr.ch/srf-meteo/v2/geolocations?latitude=47") is None
    _, _, gekuerzt = m._kuerze({"Case": list(range(20))}, None)
    assert len(gekuerzt["Case"]) == m.ZEILEN


def test_die_schutzregeln_nennen_die_container_des_servers():
    """Sonst schuetzt die Regel eine Liste, die der Server gar nicht liest.

    `_fetch_filtered` bekommt den Containerpfad als Argument — `("Items",)` fuer
    Abstimmungen, `("Elections", "Election")` fuer Wahlen —, und
    `_case_ids_in_range` liest `Case`. Der geschuetzte Schluessel muss der
    letzte Teil dieses Pfades sein; steht er woanders, laeuft der Schutz ins
    Leere und der Ordner waechst wieder auf 16 MB oder die Treffer verschieben
    sich.
    """
    m = recorder()
    quelle = (WURZEL / "src" / "srgssr_mcp" / "tools" / "polis.py").read_text(encoding="utf-8")
    erwartet = {
        "/polis-api/v2/votations": '_fetch_filtered("votations", ("Items",)',
        "/polis-api/v2/elections": '_fetch_filtered("elections", ("Elections", "Election")',
        "/polis-api/v2/cases": '_as_items(data, "Case")',
    }
    nach_muster = {s.muster: s for s in m.SCHUTZ}
    for muster, beleg in erwartet.items():
        assert muster in nach_muster, f"keine Schutzregel fuer {muster}"
        assert beleg in quelle, (
            f"der Server ruft {muster} nicht mehr so ab — die Schutzregel "
            f"`{nach_muster[muster].schluessel}` ist womoeglich falsch geworden"
        )
        assert nach_muster[muster].schluessel in beleg, (
            f"geschuetzt wird `{nach_muster[muster].schluessel}`, der Server liest {beleg}"
        )
    assert all(s.grund for s in m.SCHUTZ), "eine Schutzregel steht ohne Begruendung da"


def test_der_nachweis_nennt_schluessel_datum_und_pruefsumme(tmp_path, monkeypatch):
    """Ein Nachweis ohne diese drei ist eine undatierte Behauptung ueber die Quelle."""
    m = recorder()
    monkeypatch.setattr(m, "FIXTURES", tmp_path)
    _http._token_cache["access_token"] = None
    monkeypatch.delenv("SRGSSR_CONSUMER_KEY", raising=False)
    monkeypatch.delenv("SRGSSR_CONSUMER_SECRET", raising=False)

    antwort = m.Antwort(
        schluessel=f"{_http.BASE_URL}/srf-meteo/v2/geolocationNames?name=Bern",
        text='{"geolocations": []}',
        werkzeuge=["srgssr_weather_search_location"],
        dateiname="weather_search_1.json",
        sha256="abc123",
        bytes=42,
        gekuerzt_von=10,
        behalten=3,
    )
    m._schreibe_provenance([antwort], "2026-08-16")
    text = (tmp_path / "PROVENANCE.md").read_text(encoding="utf-8")

    assert "Aufgezeichnet am **2026-08-16**" in text
    assert "## `weather_search_1.json`" in text
    assert "name=Bern" in text
    assert "`abc123`" in text
    assert "3 von 10 Listeneintraegen" in text
    assert "Kein Token, keine Header" in text


def test_der_nachweis_geht_selbst_durch_die_geheimnis_pruefung(tmp_path, monkeypatch):
    """Die Schluessel stehen im Nachweis — also muss auch er geprueft werden.

    Eine Pruefung, die nur die Fixture-Dateien abdeckt, liesse die eine Datei
    aus, die ausdruecklich zum Lesen gedacht ist.
    """
    m = recorder()
    monkeypatch.setattr(m, "FIXTURES", tmp_path)
    _http._token_cache["access_token"] = TOKEN

    antwort = m.Antwort(
        schluessel=f"{_http.BASE_URL}/x?token={TOKEN}",
        text="{}",
        werkzeuge=["srgssr_weather_current"],
        dateiname="x_1.json",
    )
    with pytest.raises(SystemExit):
        m._schreibe_provenance([antwort], "2026-08-16")
    assert not (tmp_path / "PROVENANCE.md").exists(), "der Nachweis wurde trotzdem geschrieben"


# --------------------------------------------------------------------------
# Der Lauf ohne Credentials
# --------------------------------------------------------------------------


async def test_ohne_credentials_bricht_der_lauf_mit_begruendung_ab(monkeypatch, capsys):
    """Und zwar bevor eine Anfrage rausgeht.

    Die Meldung nennt den Workflow, der die Credentials hat. Ein blosses
    «401 Unauthorized» am Ende eines halben Laufs saehe aus wie ein Fehler der
    Quelle.
    """
    m = recorder()
    monkeypatch.delenv("SRGSSR_CONSUMER_KEY", raising=False)
    monkeypatch.delenv("SRGSSR_CONSUMER_SECRET", raising=False)

    with respx.mock:
        route = respx.route().mock(return_value=httpx.Response(200, json={}))
        code = await m.main()

    assert code == 2
    assert not route.called, "ohne Credentials ging trotzdem eine Anfrage raus"
    meldung = capsys.readouterr().err
    assert "record-fixtures.yml" in meldung, "die Meldung nennt den Weg nicht"


def test_der_schlaf_haengt_am_modul_alias():
    """`asyncio.sleep` selbst zu patchen entschaerft die Mechanik im ganzen Prozess."""
    import asyncio
    import inspect

    m = recorder()
    assert m._sleep is asyncio.sleep
    quelle = inspect.getsource(m._fahre)
    assert "await _sleep(" in quelle
    assert "asyncio.sleep" not in quelle


@respx.mock
async def test_ein_halb_ausgefallenes_ergebnis_gilt_nicht_als_aufgezeichnet(geschlossener_client):
    """`srgssr_daily_briefing` faellt nicht um — es legt den Ausfall als Feld ab.

    Der erste echte Lauf ging genau daran vorbei: die Wetter-Haelfte des
    Briefings fiel aus, das Werkzeug gab ein gueltiges Modell zurueck, und die
    fehlende `forecastpoint`-Antwort landete nie im Ordner. Gemeldet hat das
    nichts; aufgefallen ist es erst beim Abspielen, wo eine Anfrage ohne
    Aufzeichnung ein Fehler ist.

    Eine Pruefung auf der obersten Ebene kann das nicht sehen — deshalb sucht
    `_entartet` bis in die Felder.
    """
    m = recorder()
    mocke_token()
    # EPG antwortet, Wetter nicht: genau die halbe Degradation.
    respx.get(url__startswith=f"{_http.BASE_URL}/epg").mock(
        return_value=httpx.Response(200, json={"channel": {}, "programs": []})
    )
    respx.get(url__startswith=f"{_http.BASE_URL}/srf-meteo").mock(
        return_value=httpx.Response(500, json={"kaputt": True})
    )
    monkey = pytest.MonkeyPatch()
    monkey.setattr(m, "VERSUCHE", 1)
    monkey.setattr(m, "_sleep", lambda _s: asyncio.sleep(0))
    try:
        with pytest.raises(RuntimeError) as fehler:
            await m._fahre(
                m.Aufruf(
                    "briefing",
                    "srgssr_daily_briefing",
                    "DailyBriefingInput",
                    {
                        "business_unit": BusinessUnit.SRF,
                        "channel_id": "srf-1",
                        "date": "2026-08-15",
                        "latitude": 47.37,
                        "longitude": 8.54,
                    },
                )
            )
    finally:
        monkey.undo()
    assert "Ausfall in" in str(fehler.value), fehler.value
    assert "weather" in str(fehler.value), f"das ausgefallene Feld wird nicht benannt: {fehler.value}"


def test_entartet_findet_den_fehler_auch_ganz_oben_und_nirgends():
    """Die beiden Randfaelle, sonst waere die Suche oben blind oder ueberall fuendig."""
    m = recorder()
    from srgssr_mcp._models import ToolErrorResponse

    fehler = ToolErrorResponse(error_type="ValueError", message="kaputt")
    assert m._entartet(fehler) == ["(oben)"]
    assert m._entartet(None) == []
    assert m._entartet("ein String") == []
