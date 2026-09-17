"""Die Zielrevision an der Drahtform gemessen, nicht an den SDK-Konstanten.

`tests/test_protocol_version.py` haelt die beiden Revisionen gegen
`mcp.types.version` und schreibt seine eigene Schwaeche hin: «dieses Repo baut
keine ASGI-App, durch die sich ein `initialize` schicken liesse … Das ist die
schwaechere Form». Das war falsch — `MCPServer.streamable_http_app()` gibt es,
und `httpx.ASGITransport` fuehrt eine Anfrage ohne Socket hindurch. Diese Datei
schickt sie.

Was der Unterschied wert ist, zeigt der erste Lauf. Gemessen am 17.9.2026
gegen `mcp` 2.2.0, bei 425 gruenen Tests und 96 % Coverage:

* Jedes einzelne `tools/call` kam mit ``isError: true`` zurueck. Die 15 Tools
  riefen ``ctx.info("... invoked", business_unit=bu)`` — die Signatur von
  FastMCP 1.x. Auf 2.x heisst sie ``info(data, *, logger_name=None)``, also
  ``TypeError: Context.info() got an unexpected keyword argument``. Kein Test
  hat je ein echtes `Context` durchgegeben; der eine, der ueberhaupt eines
  durchgab, brachte ein ``_StubCtx`` mit ``**extra`` mit.
* An jeder Antwort hing `serverInfo` mit ``"version": ""``.

Beides war aus dem Prozess heraus nicht zu sehen und stand auf der Drahtform
sofort da. Deshalb liegt die Zusicherung hier und nicht an einem Dict.
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pytest
import respx
from mcp.server.mcpserver import Context, MCPServer
from mcp.shared.exceptions import MCPDeprecationWarning
from mcp.types.version import LATEST_HANDSHAKE_VERSION, LATEST_MODERN_VERSION

from srgssr_mcp import __version__
from srgssr_mcp import server as srv
from srgssr_mcp._app import PROTOCOL_VERSION, mcp

# `localhost:8000` und nicht `test`: `streamable_http_app()` schaltet ohne
# eigenes `transport_security` den DNS-Rebinding-Schutz ein und erlaubt
# `127.0.0.1:*`, `localhost:*`, `[::1]:*` — ein Host ohne Port faellt mit
# HTTP 421 durch, bevor irgendein Handler laeuft.
ENDPOINT = "http://localhost:8000/mcp"

# Der Envelope, der eine Verbindung in die moderne Aera schaltet. Den Ausschlag
# gibt allein der Versions-Schluessel (`_has_modern_envelope` im SDK); die
# beiden anderen sind laut Spec Pflicht und fehlen hier nicht, damit der
# Klassifikator nicht mit INVALID_PARAMS antwortet statt den Handler zu fahren.
ENVELOPE: dict[str, Any] = {
    "io.modelcontextprotocol/protocolVersion": "2026-07-28",
    "io.modelcontextprotocol/clientCapabilities": {},
    "io.modelcontextprotocol/clientInfo": {"name": "pytest", "version": "0"},
}

SERVER_INFO_META_KEY = "io.modelcontextprotocol/serverInfo"

# Minimale gueltige Argumente je Tool. Ausgeschrieben statt generiert: eine
# Generierung aus dem inputSchema wuerde dieselbe Annahme zweimal fahren und
# koennte sie nicht widerlegen.
TOOL_ARGUMENTE: dict[str, dict[str, Any]] = {
    "srgssr_epg_get_programs": {"business_unit": "srf", "channel_id": "srf-1", "date": "2026-04-30"},
    "srgssr_weather_search_location": {"query": "Zürich"},
    "srgssr_weather_current": {"latitude": 47.37, "longitude": 8.54},
    "srgssr_weather_forecast_24h": {"latitude": 47.37, "longitude": 8.54},
    "srgssr_weather_forecast_7day": {"latitude": 47.37, "longitude": 8.54},
    "srgssr_daily_briefing": {
        "business_unit": "srf",
        "channel_id": "srf-1",
        "date": "2026-04-30",
        "latitude": 47.37,
        "longitude": 8.54,
    },
    "srgssr_video_get_shows": {"business_unit": "srf"},
    "srgssr_video_get_episodes": {"business_unit": "srf", "show_id": "abc"},
    "srgssr_video_get_livestreams": {"business_unit": "srf"},
    "srgssr_audio_get_shows": {"business_unit": "srf", "channel_id": "abc"},
    "srgssr_audio_get_episodes": {"business_unit": "srf", "show_id": "abc"},
    "srgssr_audio_get_livestreams": {"business_unit": "srf"},
    "srgssr_polis_get_votations": {"year_from": 2020},
    "srgssr_polis_get_votation_results": {"votation_id": "v1"},
    "srgssr_polis_get_elections": {"year_from": 2020},
}


@asynccontextmanager
async def drahtform(server: MCPServer | None = None) -> AsyncIterator[httpx.AsyncClient]:
    """Ein HTTP-Client, der in die echte ASGI-App des Servers spricht.

    `json_response=True`, weil die Zusicherungen hier den Antwortkoerper
    lesen: im SSE-Modus schiebt das SDK dasselbe Resultat als Event-Rahmen
    hinaus, was nichts anderes prueft und das Parsen verdoppelt.
    """
    ziel = mcp if server is None else server
    app = ziel.streamable_http_app(json_response=True)
    async with ziel.session_manager.run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport) as client:
            yield client


async def modern(
    client: httpx.AsyncClient,
    method: str,
    params: Mapping[str, Any] | None = None,
    *,
    name: str | None = None,
    meta: Mapping[str, Any] | None = None,
) -> httpx.Response:
    """Eine moderne Einzelanfrage: ein JSON-RPC-Request rein, eine Antwort raus.

    Die `mcp-method`- und `mcp-name`-Kopfzeilen sind nicht Zierde: der
    Klassifikator lehnt die Anfrage mit HEADER_MISMATCH (-32020) ab, wenn sie
    fehlen oder vom Koerper abweichen. Wer sie weglaesst, misst diese Absage
    und nicht den Server.
    """
    headers = {
        "content-type": "application/json",
        "accept": "application/json, text/event-stream",
        "mcp-protocol-version": "2026-07-28",
        "mcp-method": method,
    }
    if name is not None:
        headers["mcp-name"] = name
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": {**(params or {}), "_meta": {**ENVELOPE, **(meta or {})}},
    }
    return await client.post(ENDPOINT, json=body, headers=headers)


async def handshake(client: httpx.AsyncClient, asked: str) -> Mapping[str, Any]:
    """Die alte Aera: ein `initialize` ohne Envelope, wie heutige Clients es senden."""
    response = await client.post(
        ENDPOINT,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": asked,
                "capabilities": {},
                "clientInfo": {"name": "pytest", "version": "0"},
            },
        },
        headers={"content-type": "application/json", "accept": "application/json, text/event-stream"},
    )
    assert response.status_code == 200, response.text
    return response.json()["result"]


# ---------------------------------------------------------------------------
# Die moderne Aera
# ---------------------------------------------------------------------------


async def test_eine_moderne_anfrage_braucht_keinen_handshake() -> None:
    """`server/discover` statt `initialize` — und ohne `Mcp-Session-Id`."""
    async with drahtform() as client:
        response = await modern(client, "server/discover")

    assert response.status_code == 200, response.text
    result = response.json()["result"]
    assert result["supportedVersions"] == [PROTOCOL_VERSION]
    assert result["resultType"] == "complete"
    assert "Mcp-Session-Id" not in response.headers


async def test_jede_antwort_nennt_die_version_dieses_builds() -> None:
    """Der Befund, der diese Datei begruendet.

    In der modernen Aera gibt es kein `initialize`-Resultat, das die
    Server-Identitaet einmal pro Verbindung tragen koennte; das SDK haengt sie
    an das `_meta` **jedes** Resultats. Ohne `version=` am Konstruktor steht
    dort der Leerstring — formal ein String, inhaltlich keine Auskunft, und ein
    Client kann nicht sagen, mit welchem Build er spricht.
    """
    async with drahtform() as client:
        for method in ("server/discover", "tools/list", "prompts/list", "resources/templates/list"):
            response = await modern(client, method)
            assert response.status_code == 200, response.text
            info = response.json()["result"]["_meta"][SERVER_INFO_META_KEY]
            assert info["name"] == "srgssr_mcp"
            assert info["version"] == __version__, f"{method} nennt version={info['version']!r}"
            assert info["version"], f"{method} traegt eine leere Version"


async def test_die_version_am_draht_ist_die_des_pakets_und_kein_platzhalter() -> None:
    """Gegenprobe zur Zusicherung darueber.

    `info["version"] == __version__` waere auch mit zwei leeren Strings erfuellt
    — und genau dieser Fall lag vor. Ohne Installation gibt `__version__` den
    Marker `0.0.0+source`; der ist eine Auskunft, der Leerstring nicht.
    """
    assert __version__
    assert __version__ != ""
    async with drahtform() as client:
        response = await modern(client, "tools/list")

    info = response.json()["result"]["_meta"][SERVER_INFO_META_KEY]
    assert info["version"] == __version__


async def test_die_auflistenden_methoden_tragen_den_frischehinweis_am_draht() -> None:
    """SEP-2549 aus der Sicht des Clients.

    `test_cache_hints.py` prueft dasselbe durch eine `ClientSession`. Hier steht
    es auf der Drahtform, weil `ttlMs` und `cacheScope` Felder des Resultats
    sind und nicht Eigenschaften eines Objekts.
    """
    async with drahtform() as client:
        for method in ("server/discover", "tools/list", "resources/list", "prompts/list"):
            result = (await modern(client, method)).json()["result"]
            assert result["ttlMs"] == 300_000, f"{method}: ttlMs={result.get('ttlMs')}"
            assert result["cacheScope"] == "public", f"{method}: {result.get('cacheScope')}"


async def test_ein_initialize_ist_auf_einer_modernen_verbindung_kein_einstieg() -> None:
    """Die beiden Aeren mischen sich nicht: wer modern eroeffnet, bleibt modern."""
    async with drahtform() as client:
        response = await modern(
            client,
            "initialize",
            {"protocolVersion": "2026-07-28", "capabilities": {}, "clientInfo": {"name": "pytest", "version": "0"}},
        )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == -32601


@pytest.mark.parametrize(
    "method",
    [
        "ping",
        "logging/setLevel",
        "resources/subscribe",
        "resources/unsubscribe",
        "tasks/list",
    ],
)
async def test_die_zurueckgezogenen_methoden_antworten_nicht_mehr(method: str) -> None:
    """Was 2026-07-28 aus dem Vokabular genommen hat, ist hier wirklich weg.

    Steht eine dieser Methoden eines Tages wieder, hat das SDK die Revision
    anders geschnitten als angenommen — dann ist die Aufteilung in
    `test_protocol_version.py` neu zu bewerten, nicht diese Liste zu kuerzen.
    """
    async with drahtform() as client:
        response = await modern(client, method, {})

    assert response.json()["error"]["code"] == -32601, response.text


# ---------------------------------------------------------------------------
# Die Handshake-Aera — gemessen statt aus einer Konstante gelesen
# ---------------------------------------------------------------------------


async def test_der_handshake_deckelt_bei_der_dokumentierten_revision() -> None:
    """Die READMEs behaupten diese Obergrenze; hier wird sie abgefragt.

    `test_protocol_version.py` haelt sie gegen `LATEST_HANDSHAKE_VERSION` — das
    prueft, was das SDK *sagt*, nicht, was der Server *antwortet*. Beides kann
    auseinandergehen, sobald am Konstruktor oder an `run()` etwas zur Aushandlung
    beitraegt.
    """
    async with drahtform() as client:
        assert (await handshake(client, "2025-06-18"))["protocolVersion"] == "2025-06-18"
        assert (await handshake(client, LATEST_HANDSHAKE_VERSION))["protocolVersion"] == LATEST_HANDSHAKE_VERSION
        # Die Kernaussage: ein Client, der nach der modernen Revision fragt,
        # bekommt die Obergrenze der alten zurueck, nicht das Erfragte.
        assert (await handshake(client, LATEST_MODERN_VERSION))["protocolVersion"] == LATEST_HANDSHAKE_VERSION
        assert (await handshake(client, "2099-01-01"))["protocolVersion"] == LATEST_HANDSHAKE_VERSION


async def test_der_handshake_deklariert_keine_logging_capability() -> None:
    """Der dritte Grund, warum die `ctx.info`-Aufrufe weg sind.

    Ein Server darf `notifications/message` nur senden, wenn er die
    Capability deklariert hat. Diese hier tut es nicht — auch in der alten
    Aera waere also nichts angekommen, selbst mit richtiger Signatur.
    """
    async with drahtform() as client:
        result = await handshake(client, LATEST_HANDSHAKE_VERSION)

    assert "logging" not in result["capabilities"]
    assert set(result["capabilities"]) >= {"prompts", "resources", "tools"}
    assert result["serverInfo"]["version"] == __version__


# ---------------------------------------------------------------------------
# Werkzeuge ueber die Drahtform
# ---------------------------------------------------------------------------


@pytest.fixture
def upstream() -> AsyncIterator[respx.MockRouter]:
    """Jede SRG-SSR-Antwort auf einen leeren Rumpf gemockt.

    Absichtlich inhaltsleer: hier geht es nicht ums Parsen — das pruefen die
    Fixture- und Unit-Tests mit echten aufgezeichneten Antworten. Hier geht es
    darum, dass der Rumpf eines Tools von der ersten bis zur letzten Zeile
    durchlaeuft, wenn ein echtes `Context` eingespritzt ist. Ein leerer Rumpf
    fuehrt auf den leeren Trefferpfad, der ein regulaeres Resultat liefert —
    nicht auf `isError`.
    """
    srv._token_cache["access_token"] = "test-token"
    srv._token_cache["expires_at"] = time.time() + 3600
    with respx.mock(assert_all_called=False) as router:
        router.get(url__startswith="https://api.srgssr.ch").mock(return_value=httpx.Response(200, json={}))
        yield router


async def test_jedes_werkzeug_laeuft_mit_echtem_context_durch(upstream: respx.MockRouter) -> None:
    """Der Test, der gefehlt hat.

    Die Suite rief die Tool-Funktionen direkt auf, wo `ctx` auf `None`
    defaultet — der `if ctx is not None`-Zweig lief nie, und der
    Coverage-Bericht fuehrte genau diese 14 Zeilen als nicht ausgefuehrt. Ueber
    die Drahtform spritzt das SDK ein echtes `Context` ein, und damit kommt
    heraus, was die direkte Form nicht zeigen kann.
    """
    async with drahtform() as client:
        for name, argumente in TOOL_ARGUMENTE.items():
            response = await modern(client, "tools/call", {"name": name, "arguments": {"params": argumente}}, name=name)
            assert response.status_code == 200, f"{name}: {response.text}"
            result = response.json()["result"]
            assert not result.get("isError"), (
                f"{name} antwortete mit isError. Text: {json.dumps(result.get('content'))[:300]}"
            )


async def test_ein_werkzeug_mit_der_alten_kontext_signatur_faellt_hier_auf() -> None:
    """Gegenprobe: hat der Test darueber Zaehne?

    Ein gruener Test ueber 15 Tools sagt nichts, solange nicht gezeigt ist,
    dass er den Fehler ueberhaupt sehen wuerde. Also derselbe Weg, dieselbe
    Drahtform, ein Tool mit genau der Signatur, die im `src/` stand — und die
    Zusicherung, dass sie als `isError` herauskommt.

    `pytest.warns(MCPDeprecationWarning)` haelt zugleich fest, dass das SDK
    die Methode als abgesetzt fuehrt — die Warnung ist eine `UserWarning` und
    keine `DeprecationWarning`, ein `-W error::DeprecationWarning` sieht sie
    also nicht. Verschwindet sie, hat sich die Lage des zweiten Befundes
    geaendert und der Absatz in `tools/__init__.py` gehoert nachgelesen.
    """
    kontrolle = MCPServer("kontrolle", version="0.0.0")

    @kontrolle.tool(name="alte_signatur")
    async def alte_signatur(wert: str, ctx: Context | None = None) -> str:
        if ctx is not None:
            await ctx.info("aufgerufen", wert=wert)  # type: ignore[call-arg]
        return wert

    with pytest.warns(MCPDeprecationWarning):
        async with drahtform(kontrolle) as client:
            response = await modern(
                client,
                "tools/call",
                {"name": "alte_signatur", "arguments": {"wert": "x"}},
                name="alte_signatur",
            )

    assert response.status_code == 200, response.text
    assert response.json()["result"]["isError"] is True


async def test_die_werkzeugliste_nennt_fuenfzehn_werkzeuge() -> None:
    """Haelt die Zahl, mit der `_app.py` seinen `cacheScope` begruendet.

    Dort stand `public` sei richtig, weil «die 10 Tools» beim Import
    registriert werden und nichts pro Aufrufer gefiltert wird. Der Schluss ist
    richtig, die Zahl war nie — es sind 15. Eine Begruendung, deren Grundlage
    niemand nachgezaehlt hat, traegt nicht.
    """
    async with drahtform() as client:
        tools = (await modern(client, "tools/list")).json()["result"]["tools"]

    assert len(tools) == 15
    assert {t["name"] for t in tools} == set(TOOL_ARGUMENTE)


async def test_jedes_werkzeug_traegt_seinen_anzeigenamen_in_title() -> None:
    """Spec 2026-07-28 liest den Anzeigenamen aus `title`, nicht aus `annotations`.

    `ToolAnnotations` ist dort als Satz von Hinweisen beschrieben, «including
    descriptive properties like `title`», mit dem Zusatz, ein Client solle auf
    Annotationen eines nicht vertrauenswuerdigen Servers keine Entscheidung
    stuetzen. Gemessen ging `tools/list` ohne `title` hinaus, waehrend
    `prompts/list` und `resources/templates/list` eines trugen.
    """
    async with drahtform() as client:
        tools = (await modern(client, "tools/list")).json()["result"]["tools"]

    ohne = sorted(t["name"] for t in tools if not t.get("title"))
    assert not ohne, f"ohne title: {ohne}"


async def test_anzeigename_und_annotations_titel_stimmen_ueberein() -> None:
    """Die Kopie fuer Clients auf 2025-06-18 und aelter, die nur `annotations`
    lesen. Zwei Stellen mit derselben Aussage laufen auseinander, sobald nur
    eine gepflegt wird — das ist der einzige Grund, warum das hier steht."""
    async with drahtform() as client:
        tools = (await modern(client, "tools/list")).json()["result"]["tools"]

    abweichend = {
        t["name"]: (t.get("title"), (t.get("annotations") or {}).get("title"))
        for t in tools
        if t.get("title") != (t.get("annotations") or {}).get("title")
    }
    assert not abweichend, f"title != annotations.title: {abweichend}"


async def test_prompts_und_resource_templates_tragen_weiterhin_einen_title() -> None:
    """Die Positivkontrolle zum Befund oben: dass `title` in diesem Repo schon
    benutzt wurde, macht sein Fehlen bei den Tools zur Auslassung und nicht zu
    einer Eigenheit des SDK."""
    async with drahtform() as client:
        prompts = (await modern(client, "prompts/list")).json()["result"]["prompts"]
        templates = (await modern(client, "resources/templates/list")).json()["result"]["resourceTemplates"]

    assert prompts and all(p.get("title") for p in prompts)
    assert templates and all(t.get("title") for t in templates)


# ---------------------------------------------------------------------------
# Enum-Felder unter `strict=True`
# ---------------------------------------------------------------------------

# Werkzeuge, deren Eingabemodell ein `business_unit: BusinessUnit` traegt.
# Ausgeschrieben, damit ein neues Werkzeug mit Enum-Feld hier auffaellt und
# nicht stillschweigend unter eine Ableitung faellt.
WERKZEUGE_MIT_ENUM = (
    "srgssr_epg_get_programs",
    "srgssr_daily_briefing",
    "srgssr_video_get_shows",
    "srgssr_video_get_episodes",
    "srgssr_video_get_livestreams",
    "srgssr_audio_get_shows",
    "srgssr_audio_get_episodes",
    "srgssr_audio_get_livestreams",
)


@pytest.mark.parametrize("name", WERKZEUGE_MIT_ENUM)
async def test_ein_enum_feld_nimmt_den_string_aus_seinem_eigenen_schema(name: str, upstream: respx.MockRouter) -> None:
    """Der dritte Befund, und der mit der groessten Reichweite.

    Die Eingabemodelle fahren `ConfigDict(strict=True)`. Fuer ein Enum heisst
    strikt bei Pydantic: es muss eine Enum-*Instanz* sein. Ueber die Drahtform
    kommt ein JSON-String, also `is_instance_of` und `isError` — und zwar fuer
    genau den Wert, den das veroeffentlichte `inputSchema` des Werkzeugs als
    `{"enum": [...], "type": "string"}` ausweist. Acht der 15 Werkzeuge waren
    damit von keinem Client aufrufbar.

    Zu sehen war das von innen nicht: jeder Unit-Test baut sein Eingabemodell
    in Python und uebergibt `BusinessUnit.SRF`, also bereits die Instanz. Der
    JSON-Weg kam in der Suite nicht vor.
    """
    async with drahtform() as client:
        response = await modern(
            client,
            "tools/call",
            {"name": name, "arguments": {"params": TOOL_ARGUMENTE[name]}},
            name=name,
        )

    result = response.json()["result"]
    assert not result.get("isError"), f"{name}: {json.dumps(result.get('content'))[:400]}"


@pytest.mark.parametrize("wert", ["SRF", "srf ", "xx", "", 1, None])
async def test_die_mitgliedschaft_bleibt_geprueft(wert: object, upstream: respx.MockRouter) -> None:
    """Gegenprobe zur Zusicherung darueber: `strict=False` am Enum-Feld ist
    keine Lockerung, sondern nur die Aufhebung der Instanz-Forderung.

    Ohne diesen Test wuerde ein `model_config` ohne `strict` denselben gruenen
    Lauf erzeugen — und dabei auch `latitude="47.0"` durchlassen. Deshalb
    zusaetzlich die Zeile unten, die genau das nachprueft.
    """
    async with drahtform() as client:
        response = await modern(
            client,
            "tools/call",
            {
                "name": "srgssr_epg_get_programs",
                "arguments": {"params": {"business_unit": wert, "channel_id": "srf-1", "date": "2026-04-30"}},
            },
            name="srgssr_epg_get_programs",
        )

    result = response.json()["result"]
    assert result.get("isError") is True, f"business_unit={wert!r} wurde angenommen"


async def test_der_rest_des_modells_bleibt_strikt(upstream: respx.MockRouter) -> None:
    """Die zweite Haelfte derselben Gegenprobe.

    `strict=True` steht an diesen Modellen aus einem Grund (SDK-002): eine
    Zahl, die als String kommt, ist ein Fehler des Aufrufers und keine
    Bequemlichkeit. Faellt dieser Test, hat jemand `strict` ganz vom
    `model_config` genommen statt es am Enum-Feld aufzuheben — und damit mehr
    geoeffnet als der Befund verlangt.
    """
    async with drahtform() as client:
        response = await modern(
            client,
            "tools/call",
            {
                "name": "srgssr_daily_briefing",
                "arguments": {
                    "params": {
                        "business_unit": "srf",
                        "channel_id": "srf-1",
                        "date": "2026-04-30",
                        "latitude": "47.37",
                        "longitude": 8.54,
                    }
                },
            },
            name="srgssr_daily_briefing",
        )

    assert response.json()["result"].get("isError") is True, "latitude als String wurde angenommen"


# ---------------------------------------------------------------------------
# Die uebrigen Primitive
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("uri", ["epg://srf/srf-1/2026-04-30", "votation://v1"])
async def test_eine_resource_ist_ueber_die_moderne_drahtform_lesbar(uri: str, upstream: respx.MockRouter) -> None:
    """Dieselbe Frage wie bei den Werkzeugen, fuer die zweite Haelfte der Oberflaeche.

    Die `epg://`- und `votation://`-Vorlagen tragen ihre Parameter als
    Pfadsegmente und laufen nicht durch ein `strict=True`-Modell — der
    Enum-Befund oben trifft sie also nicht. Dass sie durchlaufen, stand aber
    auch nicht fest: gemessen ist gemessen, und der Aufwand ist eine Zeile.
    """
    async with drahtform() as client:
        response = await modern(client, "resources/read", {"uri": uri}, name=uri)

    assert response.status_code == 200, response.text
    result = response.json()["result"]
    assert result["contents"], uri
    # `resources/read` liefert Inhalt und kein Verzeichnis, traegt also bewusst
    # keinen Frischehinweis — dieselbe Zusicherung wie in `test_cache_hints.py`,
    # hier an der Drahtform.
    assert result["cacheScope"] == "private"


async def test_ein_prompt_ist_ueber_die_moderne_drahtform_abrufbar() -> None:
    async with drahtform() as client:
        response = await modern(
            client,
            "prompts/get",
            {"name": "tagesbriefing_kanton", "arguments": {"location": "Zürich"}},
            name="tagesbriefing_kanton",
        )

    assert response.status_code == 200, response.text
    assert response.json()["result"]["messages"]
