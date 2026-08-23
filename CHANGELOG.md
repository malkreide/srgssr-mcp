# Änderungsprotokoll / Changelog

Alle wesentlichen Änderungen werden in dieser Datei dokumentiert.
Das Format basiert auf [Keep a Changelog](https://keepachangelog.com/de/1.0.0/).

## [Unreleased]

### Added

- **Frischehinweise auf den auflistenden Methoden** (SEP-2549, Spec
  `2026-07-28`): `ttlMs` 300000, `cacheScope` `public`. Das SDK setzt beides auf
  «sofort veraltet, nie geteilt» — wer nichts übergibt, lässt jeden Client bei
  jeder Verbindung neu auflisten. `resources/read` und `prompts/get` bleiben
  ohne Hinweis: das wäre eine Zusicherung über den Inhalt statt über das
  Verzeichnis.

- **Der Protokoll-Pin sicherte nur eine der beiden Spec-Aeren.** `mcp` 2.x
  bedient zwei ueber denselben Server; die erste Anfrage einer Verbindung
  entscheidet, welche gilt: der `initialize`-Handshake deckelt bei
  `2025-11-25`, der Pro-Request-Envelope erreicht `2026-07-28`.

  Die bisherige Zusicherung lautete `PIN == LATEST_PROTOCOL_VERSION` und las
  sich vollstaendig. `LATEST_PROTOCOL_VERSION` ist aber ein Alias auf die
  MODERNE Aera — gesichert war damit die Aera, in der heute praktisch niemand
  spricht, waehrend die andere frei wandern konnte. Man sieht es dem
  Konstantennamen nicht an.

  **Der Wert der Konstante aendert sich nicht.** Er war richtig, nur
  unvollstaendig beschrieben. Neu steht er gegen `LATEST_MODERN_VERSION` —
  dieselbe Zahl, aber die Aera ist benannt —, die Handshake-Obergrenze bekommt
  eine eigene Zusicherung, und ein dritter Test haelt die Alias-Eigenschaft
  fest, damit die Falle beim naechsten Lesen benannt dasteht.

  Ohne gemessenen Teil: dieser Server baut keine ASGI-App, durch die sich ein
  `initialize` schicken liesse. Die Aushandlung steht in
  `mcp/server/runner.py::_negotiate_initialize` und haengt an keinem Transport
  — an neun Schwester-Servern gemessen, hier an den SDK-Konstanten gehalten.

  **README.de.md nannte `2025-06-18`, README.md `2026-07-28`** — dieselbe
  Angabe, zwei Werte, drei Revisionen auseinander.

  Dazu vier Stellen, die diesen Server als FastMCP-Server beschrieben: der
  Kommentar im Projektbaum und der Absatz zum `outputSchema`, je in beiden
  Sprachen. `pyproject.toml` haelt seit der Migration fest, dass `fastmcp`
  fallengelassen wurde und `mcp.server.fastmcp` ersatzlos entfernt ist. Ein
  Test prueft das jetzt ueber die ganze Datei, nicht nur ueber den
  Protokoll-Abschnitt — genau dort war es naemlich schon richtig.

  Der Import-Schutz in `_app.py` bleibt, wo er ist, und ein Test sagt jetzt
  auch, warum er nicht reicht: `SUPPORTED_PROTOCOL_VERSIONS` mischt beide Aeren
  in einer flachen, rueckwaertskompatiblen Liste. Aus einer Mitgliedschaft
  folgt weder, dass man vorne steht, noch in welcher Aera bedient wird.

### Added
- **Fixture-Recorder samt Aufnahme-Workflow — und der Befund, dass die alte
  Begründung zu weit ging.** `CLAUDE.md` hielt fest: «Fixtures: keine, und das
  ist gemessen». Die Messung stimmte (ohne Consumer Key antworten alle Basen
  mit 401), die Schlussfolgerung nicht. Nachgemessen: die 401 kommt von SRG SSR
  selbst — eigene Header, CONNECT geht durch —, der Host ist also erreichbar,
  es fehlen allein die Credentials. Und die liegen längst da, wo der nächtliche
  Live-Lauf sie nimmt.

  Neu ist deshalb beides: `scripts/record_fixtures.py` und
  `.github/workflows/record-fixtures.yml`, der ihn mit denselben Secrets fährt
  wie `live-test.yml`. Eine dokumentierte Lücke ohne den Weg, sie zu füllen,
  ist keine Lücke, sondern ein Loch mit Beschriftung.

  Eine Aufzeichnung je **Abfrage**, nicht je Endpunkt:
  `srgssr_weather_search_location` fächert über `_query_variants` in mehrere
  Suchen auf, `srgssr_daily_briefing` spannt EPG und Wetter nebenläufig, und
  drei Werkzeuge holen sich vorher eine ID — wie die Live-Suite es tut, denn
  eine fest eingetragene ID wäre in Wochen ein toter Verweis. Die Eingaben
  stammen aus `tests/test_live.py`: dass sie Treffer liefern, ist damit belegt
  und nicht behauptet.

- **`tests/test_record_fixtures.py` — der Recorder, gefahren gegen eine
  gemockte API.** Ein Recorder, den niemand fahren *und* niemand prüfen kann,
  wäre genau das plausibel aussehende, unwiderlegbare Artefakt, gegen das die
  ganze Konvention gerichtet ist. Seine Mechanik hängt nicht an den
  Credentials: Plan, Zuordnung nach Anfrage, Kürzung, Nachweis und der
  Token-Umgang lassen sich mit einem erfundenen Token vollständig prüfen.

  `test_jede_plan_eingabe_baut_ein_gueltiges_modell` fand beim Schreiben neun
  ungültige Eingaben auf einmal — `business_unit` will die Enum, nicht den
  String. Ohne diese Zusicherung hätte der erste echte Lauf sie nach dem
  Token-Refresh gemeldet, einzeln.

- **`srf-meteo` drosselt, und der Recorder machte viermal so viele Abrufe wie
  nötig.** Vier Werkzeuge lösen dieselbe Koordinate auf — `weather_current`,
  `_forecast_24h`, `_forecast_7day` und das Tagesbriefing. Der Recorder
  deduplizierte die *Aufzeichnungen* nach Schlüssel, aber nicht die
  *Anfragen*: acht Abrufe für zwei verschiedene URLs.

  Gemessen am 16.8.2026 gegen die echte API: der erste Abruf kam durch, der
  zweite auf dieselbe URL bekam `HTTP 429 Too Many Requests` und blieb über
  vier Retries und rund 50 Sekunden gedrosselt. `_EinmalHolen` beantwortet
  jetzt aus dem Bestand, was der Lauf schon geholt hat, und zwischen den
  Plan-Einträgen liegt eine Pause — ein Recorder ist Gast bei der Quelle.

  Derselbe 429 war auch der Grund für die unvollständige Aufzeichnung des
  Tagesbriefings, nur still: das Werkzeug degradiert, statt umzufallen.

  Umgehängt wird `_transport_for_url` und nicht `_transport` — httpx fragt
  zuerst `_mounts`, und die sind durch die Proxy-Konfiguration belegt. Der
  erste Versuch über `_transport` lief ins Leere, und der Test hat es gezeigt.

### Sicherheit / Security
- **Das OAuth-Token gelangt in keine Datei.** Diese API ist die einzige im
  Portfolio mit OAuth2: die Antwort von `/oauth/v1/accesstoken` trägt ein
  gültiges Bearer-Token, die Anfrage dorthin
  `Authorization: Basic <key:secret>`. Ein Recorder, der «jede Antwort» ablegt,
  committet beim ersten Lauf ein funktionierendes Token in ein öffentliches
  Repository.

  Drei Riegel, jeder einzeln gegengeprobt: die Token-URL ist ausgenommen
  (`NIE_AUFZEICHNEN`), der Schlüssel ist die URL **ohne jeden Header**, und vor
  dem Schreiben läuft `_pruefe_kein_geheimnis` über jede Datei *und* über
  `PROVENANCE.md` — sie bricht ab statt zu warnen, denn eine halb geschriebene
  Aufzeichnung ist wiederholbar, ein veröffentlichtes Token nicht.

  Der Workflow prüft danach ein zweites Mal, mit `grep` und ausserhalb des
  Programms, das er bewacht: ein Riegel, der im selben Programm sitzt wie das
  Geprüfte, fällt mit ihm.

  `test_der_token_refresh_ist_ueberhaupt_gelaufen` hält fest, dass der Refresh
  überhaupt stattfindet — sonst wäre «kein Token in den Aufzeichnungen» wahr
  und bedeutungslos.

- **`srgssr_daily_briefing` hatte keinerlei Drift-Deckung.** Von 15 Werkzeugen
  fehlte genau eines in der nächtlichen Live-Suite — ausgerechnet der
  Aggregator, der Wetter und EPG über zwei Produkte hinweg zusammenführt und
  damit an den meisten Stellen brechen kann. Er hat jetzt einen Live-Test.

  Dass die Lücke unbemerkt bestand, liegt an der Zählweise: 14 abgedeckte
  Werkzeuge sehen nach Vollständigkeit aus, solange niemand gegen die
  Werkzeugliste zählt. `tests/test_live_coverage.py` tut genau das — es liest
  die Namen aus dem Quellcode statt aus einer gepflegten Liste, die beim
  nächsten Werkzeug vergessen würde, und prüft zusätzlich, dass das Suchmuster
  überhaupt Werkzeuge findet (ein Muster, das nichts findet, macht jede Aussage
  darüber wahr).

  Der Live-Test selbst prüft beide Hälften des Briefings **einzeln**: der
  Aggregator hält den Graceful-Degradation-Vertrag und wirft nie, ein
  Upstream-Bruch erscheint deshalb als Feld und nicht als Ausnahme. Eine
  Zusicherung, die nur den Rückgabewert prüft, liesse einen Totalausfall
  durch.

### Documented
- **Warum dieser Server keine aufgezeichneten Fixtures hat** (`CLAUDE.md`,
  Teil 2). Die Portfolio-Konvention verlangt eine aufgezeichnete Antwort je
  externem Endpunkt; hier ist das ohne Consumer Key nicht möglich. Gemessen am
  15.08.2026: der Token-Endpunkt antwortet mit 401 — auch auf erfundene
  Zugangsdaten —, und alle fünf Produkt-Basen (`srf-meteo`, `videometadata`,
  `audiometadata`, `epg`, `polis-api`) ebenso. Einen 401 als Fixture abzulegen
  hiesse, ihn als das auszugeben, was die Quelle normalerweise sagt; deshalb
  liegt nichts im Repo. Die `CLAUDE.md` nennt Befund und Datum, damit die Lücke
  als Befund lesbar ist und nicht als Versäumnis; die Probe im Einzelnen steht
  im Docstring von `tests/test_live_coverage.py`, damit die nächste Sitzung sie
  nicht wiederholt. Getrennt, weil die `CLAUDE.md` kurz bleiben muss — eine
  lange wird überlesen und ist dann schlechter als keine.

- **Retry-Politik gegenüber dem SRG-SSR-Gateway** (ARCH-014). Bisher gab es
  keine: Ein einzelner Netzwerkfehler, ein Timeout oder ein 503 beendete den
  Tool-Aufruf, obwohl der nächste Versuch Sekunden später geklappt hätte.

  Wiederholt werden Netzwerkfehler, Timeouts, 5xx und 429 — vier Versuche. Ein
  4xx ausser 429 scheitert weiterhin sofort; ebenso der `ValueError` aus dem
  SSRF-Guard und aus `_raise_for_redirect`, denn ein nicht registrierter
  Basispfad antwortet auch beim vierten Mal mit 302.

- **Der Token-Endpunkt wird mitgeschützt.** Er war der stillste Ausfallpunkt
  des Servers: Ist er kurz nicht erreichbar, scheiterte *jeder* Tool-Aufruf,
  und ein 401 aus einem nicht erneuerbaren Token liest sich für Nutzende als
  «falsche Credentials» — eine Diagnose, die sie einen Schlüssel prüfen lässt,
  der nie das Problem war.

- **`Retry-After` wird gelesen und schlägt die eigene Backoff-Kurve**, in
  beiden Formen nach RFC 9110 §10.2.3 (Sekundenzahl und HTTP-Datum). Ein
  unbrauchbarer Header führt zurück auf die Kurve statt zum Absturz.

- **Backoff ist gestreut (Jitter).** `2**attempt` ist deterministisch, und
  dieser Server erzeugt den Gleichtakt ohne fremde Hilfe: Die
  Aggregations-Tools fächern über `asyncio.gather` auf, also retryen mehrere
  Requests **eines** Prozesses synchron und die Last kommt als Welle zurück.
  Exponentiell `[0.5x, 1.5x]`, auf einem `Retry-After` einseitig
  `[1.0x, 1.25x]`. Deckel von 20 s je Einzelwartezeit, angewandt **nach** dem
  Jittern — die andere Reihenfolge macht den Deckel zu gar keiner Schranke.

- **Ein Gesamtbudget von 25 s für Token-Abruf und Request zusammen.** Zwei
  getrennte Budgets hätten einen kalten Cache 25 s für den Token und 25 s für
  den Aufruf ausgeben lassen — 50 s gegen einen 30-s-Client-Default, wobei
  jede Hälfte für sich harmlos aussieht. Die Deadline wird deshalb in
  `_api_get` eröffnet und durchgereicht.

  Sie hängt an `asyncio.timeout`, nicht am httpx-Timeout: httpx begrenzt pro
  Operation, und sein Read-Timeout beginnt mit jedem Chunk von vorn — eine
  langsam tröpfelnde Antwort würde das Budget sonst überdauern, ohne dass ein
  einzelner Read abläuft.

### Fixed
- **Ein aufgebrauchtes Gesamtbudget las sich als «Unerwarteter Fehler».** Es
  wirft den builtin `TimeoutError`, `_handle_error` kannte aber nur
  `httpx.TimeoutException`. Für den Aufrufer ist beides dasselbe: Es hat zu
  lange gedauert.

- **Das Nightly wäre ohne Secrets grün geblieben.** `live-test.yml` liest
  `LIVE_TEST_CONSUMER_KEY`/`_SECRET`; fehlen sie, überspringt die
  `live_credentials`-Fixture jeden Test, pytest endet mit 0 und der Lauf meldet
  Erfolg — ohne einen einzigen Endpunkt berührt zu haben. Genau diese Form von
  blindem Nightly hat vier tote Basispfade ein Release überleben lassen. Ein
  Preflight-Schritt bricht jetzt ab, wenn die Secrets fehlen: eine fehlende
  Konfiguration ist ein Fehler, keine bestandene Prüfung.

- **Ein Drift hätte jede Nacht ein neues Issue erzeugt.** Der Failure-Handler
  rief `issues.create()` ohne Prüfung auf. Eine API, die sich ändert, bleibt
  geändert — aus einem Befund wären so pro Woche sieben Issues geworden, und
  ein zugestelltes Issue-Board wird ignoriert. Der Handler sucht jetzt das
  offene Issue mit dem Label `live-tests` und kommentiert es; erst nach dem
  Schliessen legt der nächste Fehlschlag ein neues an.

### Added
- **Explizite `permissions` in `live-test.yml`** (`contents: read`,
  `issues: write`). Der Handler braucht Schreibrechte auf Issues; ohne
  Deklaration hängt das am Repo-Default, der auf read-only stehen kann — dann
  scheitert die Meldung stillschweigend genau dann, wenn sie gebraucht wird.

## [2.0.1] - 2026-08-02

### Behoben

- **`structlog` hatte keine Obergrenze, und der Index fuehrt bereits einen Major
  oberhalb der Untergrenze.** Deklariert war `structlog>=24.1.0`; auf PyPI liegt
  `26.1.0`. Das Artefakt aendert sich nicht — die Antwort des Resolvers auf
  die naechste frische Installation schon, und genau so wurde
  `swiss-energy-mcp` 0.3.3 uninstallierbar, als `mcp` 2.0.0 das Modul entfernt
  hat, das es importierte.

  Neu `structlog>=24.1.0,<27`. Die Grenze ist gemessen, nicht geraten: dieses Paket installiert
  und importiert heute gegen `structlog 26.1.0`, die Obergrenze laesst also zu,
  was nachweislich funktioniert, und stoppt nur den naechsten, unbekannten
  Major.

Ein Abhaengigkeitsbereich erreicht die Nutzenden nur ueber ein neues
Release, daher der Versions-Bump. Am Code aendert sich nichts.

## [2.0.0] – 2026-07-31

Ein Major-Release, obwohl fast alles darin eine Reparatur ist. Der Grund für
die 2: `srgssr_audio_get_shows` verlangt neu einen Pflichtparameter, und
`srgssr_weather_current` liefert Werte aus einer anderen API mit anderer
Bedeutung. Wer auf `^1.1` pinnt, bekommt keine kompatible Fortsetzung.

Was 1.1.0 tatsächlich war: 13 der 15 Tools riefen Routen auf, die es am
Gateway nicht gibt — die Basispfade `/video/v3`, `/audio/v3`,
`/forecasts/v2.0/weather` und `/polis/v1` sind dort nicht registriert, und
video/audio verwendeten unter dem korrigierten v2-Basispfad weiterhin die
v3-Unterpfade. Vollständig funktioniert hat einzig `srgssr_epg_get_programs`;
das zusammenfassende `srgssr_daily_briefing` lieferte dank Graceful
Degradation immerhin seine EPG-Hälfte und für das Wetter einen Fehler.

Alle 15 Tools sind jetzt gegen die Live-API verifiziert (Stand 2026-07-31).
Grundlage sind die OpenAPI-Specs aus dem Developer-Portal statt Rateversuche.

### Changed (BREAKING)
- **`srgssr_audio_get_shows`: `channel_id` ist neu Pflicht.** Die v2-API listet
  Radiosendungen ausschliesslich pro Kanal; eine Liste pro Unternehmenseinheit
  gibt es nicht. Gültige IDs liefert `srgssr_audio_get_livestreams`, und der
  Fehler-Hint sagt das auch. Das Tool hat dafür ein eigenes Eingabemodell
  `AudioShowsInput` statt wie bisher `VideoShowsInput` mitzubenutzen.

- **`srgssr_weather_current` meldet keine Messung mehr, sondern eine Prognose.**
  SRF Meteo v2 bietet keinen Echtzeitwert an. «Aktuell» ist jetzt das erste
  Stundenintervall der Prognose — der ehrlichste verfügbare Wert. Ein
  gleichnamiges Tool mit anderer Semantik ist ein Bruch, auch wenn die Signatur
  gleich bleibt.

- **`srgssr_video_get_shows`: neues optionales `character_filter`.** Die
  v2-API gruppiert Sendungen nach Anfangsbuchstabe und kennt keinen
  «alles»-Aufruf. Mit `character_filter` (`a`–`z` oder `#`) ist es eine
  Abfrage; ohne fächert der Server über alle 27 Buckets auf und führt
  zusammen. Der Fan-out ist der Default, weil die Alternative — still nur
  einen Buchstaben liefern — eine Teilmenge als Gesamtkatalog ausgäbe.

- **`has_more` folgt jetzt dem `next`-Cursor der API.** v2 paginiert über ein
  opakes Token statt über Offsets und meldet keine Gesamtzahl. `total` ist
  deshalb, was der Aufruf geliefert hat, und `has_more` spiegelt, ob die API
  eine Fortsetzung anbietet — statt aus `page * page_size` geschätzt zu werden.

### Added
- **3xx-Guard in `_api_get`.** Ein Basispfad, den das Gateway nicht kennt,
  wird mit `302` auf `developer.srgssr.ch` beantwortet statt mit `404`.
  `raise_for_status()` wirft darauf zwar, aber der Fehler fiel in den
  generischen Zweig von `_handle_error` und erzeugte `API-Fehler 302:` plus
  den leeren Redirect-Body: ein Statuscode und sonst nichts — kein Endpunkt,
  kein Hinweis auf die Ursache.

  Hinter dieser Meldung haben vier tote Basispfade (`/video/v3`, `/audio/v3`,
  `/forecasts/v2.0/weather`, `/polis/v1`) ein Release überlebt. Der Guard
  nennt jetzt Pfad und Redirect-Ziel und stuft es als
  «Konfigurationsfehler» ein — was ein nicht mehr existierender Basispfad
  auch ist. Gilt für Daten- und Token-Requests gleichermassen.

  Gegenprobe: ohne den Guard liefert derselbe Test `API-Fehler 302:` mit
  leerem Body, mit ihm eine Meldung, die `tv_shows/alphabetical` und das
  Redirect-Ziel nennt.

- **Sender-Register für das EPG, direkt von der API erhoben.** Die gültigen
  Sender-IDs standen bisher nirgends; `srf1` in allen Beispielen war schlicht
  falsch, und für RTS und RSI hatte niemand belastbare Werte. Der Gateway
  nennt sie selbst: eine unbekannte Station beantwortet er mit
  `400.01.004/005/006` und zählt im `info`-Feld die zulässigen Werte auf.
  Abgefragt am 2026-07-31 für alle sechs Kombinationen:

  | Unternehmenseinheit | TV | Radio |
  |---|---|---|
  | SRF | `srf-1`, `srf-2`, `srf-info` | `srf-1`, `srf-2`, `srf-2-kultur`, `srf-3`, `srf-4`, `srf-musikwelle`, `srf-virus` |
  | RTS | `rts-1`, `rts-2`, `rts-info` | `LA1ERE`, `ESPACE2`, `COULEUR3`, `OPTION_MUSIQUE` |
  | RSI | `la-1`, `la-2` | `rete-uno`, `rete-due`, `rete-tre` |

  RTS-Radio fällt aus dem Schema — Grossbuchstaben mit Unterstrich. Ein
  geratenes `rts-1` wäre dort ebenso falsch gewesen wie das alte `rts1`.

  `EPG_STATIONS` in `tools/epg.py` hält die Werte und speist zwei Stellen: die
  Tool-Description, damit das Modell gleich eine gültige ID wählt, und den
  Fehler-Hint, damit eine falsche ID in einem Schritt korrigierbar ist. Der
  bisherige Hint verwies auf `srgssr_video_get_livestreams` — ein Umweg, denn
  jene IDs stammen aus einer anderen API und müssen mit den EPG-IDs nicht
  übereinstimmen.

  **Bewusst keine Eingabe-Validierung.** Eine harte lokale Prüfung würde einen
  Request ablehnen, den die API beantworten würde, sobald SRG SSR einen Sender
  ergänzt. Echte Daten zu verweigern ist der schlechtere Fehler. Das Register
  informiert, es blockiert nicht.

### Changed
- **Polis: Jahres- und Kantonsfilter sind jetzt echte Filter.** `PolisListInput`
  bot `year_from`, `year_to` und `canton` an — **keiner dieser Parameter
  existiert in der v2-API**. Sie wurden mitgeschickt und ignoriert: Eine Frage
  nach «Abstimmungen im Kanton Bern zwischen 2010 und 2020» lieferte alles und
  sah dabei aus wie eine gefilterte Antwort. Das ist heimtückischer als ein
  Fehler, und es ist ausgerechnet die Anker-Demo-Abfrage der README.

  Die API filtert über `locationid` und `caseid`. Beides wird jetzt aufgelöst:
  Das Kantonskürzel geht über `/locations?locationtypeid=2`, der Jahresbereich
  über `/cases` in die Abstimmungstage des Zeitraums, von denen dann nur so
  viele abgefragt werden, wie die Seitengrösse verlangt. Ein unbekanntes
  Kantonskürzel ist ein Fehler statt einer stillschweigend ungefilterten
  Liste.

  `/cases?listAllCases=true` ist laut Spec langsam und «nicht öfter als einmal
  täglich» aufzurufen; die Kantons- und Fall-Listen werden deshalb sechs
  Stunden prozessweit gecacht.

- **Polis: Response-Parsing an die gemessenen Formen angepasst.** Die Spec
  lässt die `200`-Antworten leer (`content: {}`), die JSON-Schlüssel stammen
  also aus echten Antworten (2026-07-31). Sie sind XML-abgeleitet und
  uneinheitlich: Abstimmungen liegen unter `Items`, Fälle unter `Case`, Wahlen
  eine Ebene tiefer unter `Elections.Election` — ein Dict um das Array,
  weshalb eine «nimm die erste Liste»-Heuristik danebengegriffen hätte. Datum
  ist `EventDate`, Titel `Title`.

  Wahlen tragen weder Titel noch Datum: beides steht am `Case`-Objekt daneben,
  das jetzt mitgeführt wird.

- **Ein Totalausfall im Fan-out ist ein Fehler, kein leerer Katalog.**
  Schlagen alle 27 Buckets fehl, kommt eine `ToolErrorResponse` zurück. Sonst
  hätten 27 verschluckte Fehler exakt wie 27 leere Buchstaben ausgesehen und
  das Modell hätte «SRF hat keine Sendungen» berichtet. Teilausfälle liefern
  weiter, was funktioniert hat, und protokollieren `partial_result`.

- **Live-Tests entrümpelt.** `tests/test_live.py` prüfte Strings
  (`assert "TV-Sendungen" in result`), obwohl die Tools seit SDK-002
  Pydantic-Modelle zurückgeben — die Assertions konnten gegen ein `BaseModel`
  gar nicht fehlschlagen, und `_is_error` rief `str.startswith` auf einem
  Modell auf. Dazu setzten drei Tests `response_format`, ein Feld, das es seit
  SDK-002 nicht mehr gibt und das `extra="forbid"` abgelehnt hätte. Das
  Nightly, das die Pfadfehler hätte melden sollen, war damit blind. Jetzt
  typisierte Assertions auf echte Felder.

### Fixed
- **Video- und Audio-Tools auf die tatsächlichen v2-Routen umgestellt.** Der
  Basispfad war seit 1.1.0 richtig, die Pfade darunter nicht — sie stammten
  noch aus v3 und lieferten `404`. Grundlage sind jetzt die OpenAPI-Specs aus
  dem Developer-Portal (`SRGSSR Video 2.0.4`, `SRGSSR Audio 2.0.5`), nicht mehr
  Rateversuche:

  | Tool | Alt | Neu |
  |---|---|---|
  | `srgssr_video_get_shows` | `{bu}/showList` | `/tv_shows/alphabetical?bu=&characterFilter=` |
  | `srgssr_video_get_episodes` | `{bu}/showEpisodesList/{id}` | `/latest_episodes/shows/{showId}?bu=` |
  | `srgssr_video_get_livestreams` | `{bu}/channels` | `/tv_channels?bu=` |
  | `srgssr_audio_get_shows` | `{bu}/showList` | `/radioshows/byChannel?bu=&channelId=&characterFilter=` |
  | `srgssr_audio_get_episodes` | `{bu}/showEpisodesList/{id}` | `/episodeComposition/shows/{showId}?bu=` |
  | `srgssr_audio_get_livestreams` | `{bu}/channels` | `/radio/channels?bu=` |

  `bu` ist durchgehend Query-Parameter statt Pfadsegment. Episoden liegen unter
  `episodeComposition` statt `episodeList`; die alten Feldnamen bleiben als
  Fallback.

- **Wetter-Tools auf die SRF-Meteo-v2-API umgestellt.** `WEATHER_BASE` zeigte
  auf `/forecasts/v2.0/weather` — einen Basispfad, den das Gateway nicht kennt
  (`302` aufs Developer-Portal). Laut Spec `SRF Weather 2.0.1` ist es
  `/srf-meteo/v2`.

  Der Umbau geht tiefer als ein Pfadwechsel, weil v2 anders geschnitten ist:
  Es gibt **keine getrennten `current`-, `24hour`- und `7day`-Endpunkte**. Ein
  einziger Aufruf `/forecastpoint/{geolocationId}` liefert `days`,
  `three_hours` und `hours` zusammen; die drei Tools schneiden daraus
  verschiedene Arrays.

  Auch die Feldnamen sind andere: flach und in Grossbuchstaben (`TTT_C`,
  `RRR_MM`, `FF_KMH`, `DD_DEG`, `RELHUM_PERCENT`, `TN_C`/`TX_C`,
  `symbol_code`, `date_time`) statt der verschachtelten
  `values.ttt.value`-Form. `_extract_value` entfällt damit.

  Die Standortsuche liegt neu auf `/geolocationNames` und kennt keinen
  kombinierten Suchbegriff: Postleitzahlen gehen an `zip`, alles andere an
  `name`. Die Antwort kommt mal als Array, mal als einzelnes Objekt — beides
  wird normalisiert. Zurückgegeben wird die **geolocation**-ID, nicht die ID
  des Namenseintrags, denn nur erstere funktioniert am Forecast-Endpunkt.

- **Wetter: die Koordinaten taugen nicht als `geolocationId`.** Die Spec
  beschreibt den Pfadparameter als `'[lat],[lon]'` auf vier Nachkommastellen,
  was sich liest, als könnte man sie direkt einsetzen. Gemessen am 2026-07-31:
  `/forecastpoint/47.3769,8.5417` antwortet mit `404`. Die Koordinaten werden
  jetzt zuerst über `/geolocations` in eine Stations-ID aufgelöst; findet sich
  keine, ist das ein Fehler statt einer leeren Prognose. Eine explizit
  übergebene `geolocation_id` spart den Zusatz-Request.

- **Polis-Tools auf `polis-api/v2` umgestellt.** `POLIS_BASE` zeigte auf
  `/polis/v1` — ein Basispfad, den das Gateway nicht kennt. Sechs Varianten
  hatte ich erfolglos durchprobiert; die Spec `SRGSSR Polis 2.0.2` nennt
  `/polis-api/v2`, credential-frei bestätigt (`401` statt `302`).

- **Polis-Jahresfilter las die falschen vier Ziffern.** Der zweite Live-Lauf
  holte 570 Abstimmungstage und wählte davon keinen einzigen für 2020–2024 aus
  — ohne Fehler, weil die Daten sich ja lesen liessen. Nur eben falsch.

  Die API ist durchgehend .NET-XML-abgeleitet (PascalCase,
  `EventDateSpecified`-Flags), und dazu gehört die Datumsform
  `/Date(1601164800000)/`. Die ersten vier Ziffern daraus ergeben **1601** —
  eine plausibel aussehende Jahreszahl, die jeden Filter passiert und dabei
  jeden Treffer ausschliesst. Aus einem vollständigen Datensatz wurde so ein
  leerer Zeitraum, ohne dass irgendwo etwas rot wurde.

  `_year_of` versteht jetzt beide Formen — ISO-Strings und
  Epoch-Millisekunden — und prüft das Ergebnis gegen 1800–2100. Ein Wert
  ausserhalb gilt als nicht lesbar und löst denselben `case_dates_unparseable`
  -Fehler aus wie ein fehlendes Datum, statt sich als Filter zu tarnen.

- **Polis: unlesbare Falldaten sind ein Fehler, kein leerer Zeitraum.** Lässt
  sich aus vorhandenen Fällen *kein einziges* Datum lesen, wird das gemeldet
  und die Feldnamen landen im Log unter `case_dates_unparseable` — statt als
  «keine Abstimmungen in diesem Zeitraum» durchzugehen. Daten, die sich lesen
  lassen und nur ausserhalb des Bereichs liegen, bleiben ein legitimes leeres
  Ergebnis.

- **Fehler-Hints erscheinen jetzt auch bei `400`, nicht nur bei `404`.** Eine
  unbekannte Sender-ID beantwortet das EPG mit `400`, nicht mit `404` — der
  Hint, der genau für diesen Fall geschrieben ist, hätte den Aufrufer also nie
  erreicht. `400` heisst wie `404` «deine Eingabe war falsch», und erst der
  Hint macht das reparierbar. Andere Statuscodes bleiben unberührt, inklusive
  Test dafür.

- **Live-Tests scheiterten an `RuntimeError: Event loop is closed`.** Der
  geteilte `httpx.AsyncClient` wird einmal erzeugt und für die Prozesslaufzeit
  gehalten — richtig für einen Server, falsch unter pytest-asyncio, das jedem
  Test einen frischen Event-Loop gibt. Ab dem zweiten Test erbte der Lauf einen
  Client, dessen gepoolte Verbindungen zu einem bereits geschlossenen Loop
  gehörten.

  Das sah aus wie eine kaputte API und war keine: sechs der acht
  Fehlschläge im ersten echten Live-Lauf gingen darauf zurück, nicht auf die
  Endpunkte. Eine Autouse-Fixture schliesst den Client jetzt nach jedem Test,
  analog zum bestehenden DNS-Pin-Reset.

- **Zwei Live-Tests prüften noch Strings** (`assert "Wahlen" in result`,
  `assert "Volksabstimmungen" in result`) — übersehen bei der Umstellung auf
  typisierte Returns. Gegen ein `BaseModel` iteriert `in` über die Feldnamen
  und kann nie zutreffen.

### Security
- **Die `live_credentials`-Fixture gab Key und Secret zurück.** pytest druckt
  Fixture-Werte in jeden Fehlerbericht, also standen beide im Klartext zuoberst
  in der Ausgabe jedes fehlschlagenden Live-Tests — und solche Ausgaben landen
  in Issues, Chats und Bug-Reports. Kein Test hat den Rückgabewert je benutzt;
  die Tools lesen die Zugangsdaten selbst aus der Umgebung. Die Fixture gibt
  jetzt nichts mehr zurück.

- **Egress-Allowlist wieder bei genau einem Host — und die Doku stimmt dazu.**
  Mit dem Endpunkt-Fix in 1.1.0 war `srgssr-prod.apigee.net` in `ALLOWED_HOSTS`
  gelandet; dorthin gingen seither die Basic-Auth-Client-Credentials. Die
  Sicherheitsdokumentation nannte an fünf Stellen weiterhin `{"api.srgssr.ch"}`
  als vollständige Allowlist — sie beschrieb also eine engere Vertrauensgrenze,
  als der Code zog.

  Mit echten Credentials nachgemessen: **beide Token-Endpunkte liefern 200, und
  beide Tokens verhalten sich auf allen 14 geprüften Endpunkten identisch**
  (Video, Audio, EPG, Wetter, Polis, jeweils Status und Response-Grösse
  gleich). Der zweite Host war nie nötig. Die Begründung in PR #46 stützte sich
  auf die Fault-Meldung `"Invalid access token"` — die der Gateway aber auf
  *jeden* unauthentifizierten Request an einen v2-Basepath liefert, also kein
  Beleg für einen Issuer-Mismatch ist. Die tatsächliche Ursache lag bei den
  Pfaden.

  Der Host ist damit wieder draussen, statt nur dokumentiert zu sein: keine
  Client-Credentials mehr an multi-tenant-Infrastruktur unter Google-Betrieb.
  `test_allowed_hosts_is_pinned` pinnt die Menge jetzt explizit auf
  `{"api.srgssr.ch"}` — die bestehenden Wächter-Tests prüften nur
  *Mitgliedschaft* und werden durch jede Erweiterung per Konstruktion grün, sie
  konnten den neuen Egress-Zielhost gar nicht bemerken.

  Für Betreiber relevant: `docs/network-egress.md` liefert
  Kubernetes-NetworkPolicy-, Cilium-FQDN-, AWS-Security-Group- und
  Cloudflare-Zero-Trust-Beispiele. Wer sie unter 1.1.0 übernommen hätte, hätte
  den Token-Endpunkt ausgesperrt und damit jeden Request.

## [1.1.0] – 2026-07-30

### Fixed
- **API-Basispfade und EPG-Endpunkt korrigiert** (Basis: PR #46 von @aburossi).
  `/video/v3` und `/audio/v3` sind bei Apigee nicht mehr als Basepath
  registriert — sie antworten mit **302 auf `developer.srgssr.ch`**, exakt wie
  ein frei erfundener Pfad. Der Aufrufer sah davon nur `API-Fehler 302:` samt
  leerem Redirect-Body — Statuscode und sonst nichts. Neu
  `/videometadata/v2` und `/audiometadata/v2`.

  *Korrektur (2026-07-31):* Dieser Eintrag behauptete ursprünglich,
  `raise_for_status()` greife bei 302 nicht und `resp.json()` sei auf HTML
  gelaufen. Das stimmt nicht — httpx wirft auch bei 3xx. Der Fehler landete im
  generischen Zweig von `_handle_error`, nicht in einem `JSONDecodeError`. Am
  Befund und am Fix ändert das nichts, an der Begründung schon.

  Das EPG adressiert einen Tag über `/{bu}/{tv|radio}/stations/{station}` —
  Unternehmenseinheit und Sendertyp sind Pfadsegmente, nicht Query-Parameter.
  Dafür kommt `broadcast_type` (`tv`/`radio`, Default `tv`) als neues Feld an
  `srgssr_epg_get_programs`. Die Antwort heisst `programs` (nicht
  `programList`) und trägt die Zeit in `dateTimes.startTime`, den Text in
  `shortDescription`/`longDescription`; die alten Feldnamen bleiben als
  Fallback erhalten.

  Die `epg://{bu}/{channel_id}/{date}`-Resource hing am selben alten Pfad und
  wird mitgezogen. URL-Bau und Programm-Extraktion liegen jetzt in
  `_epg_station_url()` / `_extract_raw_programs()` in `tools/epg.py`, die sich
  Tool und Resource teilen — die beiden Oberflächen können nicht mehr auf
  verschiedene Endpunkte auseinanderlaufen. Die Resource-URI hat kein Feld für
  den Sendertyp und ist damit TV-only; für Radio das Tool verwenden. Das steht
  jetzt auch in der Resource-Beschreibung.

  Sender-IDs folgen der Stations-Schreibweise (`srf-1` statt `srf1`);
  Tool-Beispiele, Prompt-Default, READMEs, `EXAMPLES.md` und der Live-Test sind
  nachgezogen.

  Die EPG-Mocks in `tests/test_unit.py` matchen exakte URLs statt eines
  Präfix-Patterns — ein Mock, der jeden Pfad unter `EPG_BASE` akzeptiert, wäre
  über den nicht migrierten Resource-Aufruf grün durchgelaufen. Drei neue
  Tests decken die Station-Response-Form, den `radio`-Pfadsegment-Fall und den
  Endpunkt der Resource ab.

### Removed
- **`fastmcp` als Abhängigkeit entfernt — nichts importierte es.** Es war ein
  Rest aus der Zeit, in der dieser Server `mcp` transitiv darüber bezog; mit
  der direkten `mcp`-Deklaration wurde es überflüssig und blieb trotzdem
  stehen. Nichts schlug fehl, deshalb fiel es nicht auf.

  Gemessen in frischen venvs, nur Runtime-Abhängigkeiten: **84 → 44 Pakete**,
  also 40 weniger, und keines kommt hinzu. Was mit verschwindet, ist der Punkt:
  `redis` und `burner-redis`, `py-key-value-aio`, `pydocket`,
  `prometheus_client`, `keyring`/`SecretStorage`/`jeepney`, `Authlib`,
  `joserfc`, `websockets`, `cronsim`, `jsonschema-path`. Ein Redis-Client, ein
  Keyring-Stack und eine OAuth-Bibliothek wurden in einen read-only Server über
  öffentliche Daten installiert, wegen einer ungenutzten Zeile.

  `tests/test_dependencies.py` hält das offen in beide Richtungen: der Test
  prüft *Gleichheit* von „deklariert" und „importiert", nicht bloss Abwesenheit.
  Ein legitimer Wiedereinzug von `fastmcp` verlangt also die Deklaration zurück,
  statt den Test zu löschen. Ein zweiter Test prüft den Scanner selbst gegen
  `mcp`, damit ein kaputter Import-Scan nicht jede Gleichheit trivial erfüllt.
  Beide Richtungen sind mutationsgetestet.

  Die Dependabot-Gruppen nennen `fastmcp` nicht mehr — das Pattern wäre mit der
  Abhängigkeit toter Code geworden.

  Geprüft: 162 passed / 14 deselected (156 plus die sechs neuen Tests),
  Coverage 96.7 % gegen das 80-%-Gate, `ruff check src/` clean, und ein Install
  in einem frischen venv startet den Server mit allen 15 Tools. Kein
  `yaml`-Import im Projekt, obwohl `PyYAML` mit wegfällt.

### Changed
- **Migration auf die `mcp` 2.x Server-API.** Pin von `>=1.28.1,<2` auf
  `>=2.0.0,<3`. Die Untergrenze ist hart: 2.0.0 hat `mcp.server.fastmcp` ohne
  Kompatibilitätsschicht entfernt, dieser Code läuft also gar nicht mehr auf
  1.x — ein `>=1.x`-Bereich würde einen Resolver eine Version wählen lassen,
  die beim Import scheitert. `FastMCP` → `MCPServer`.

  Bestehende Clients sehen keinen Unterschied: der Legacy-`initialize`-Handshake
  deckelt weiterhin bei 2025-11-25 — nachgemessen, nicht aus einem
  Konstantennamen geschlossen; wer `2026-07-28` anfragt, bekommt `2025-11-25`
  zurück. mcp 2.x bedient über denselben Server aber eine zweite, „moderne"
  Ära (Per-Request-Envelope; die erste Anfrage des Clients entscheidet), die
  2026-07-28 erreicht. Ein 2.x-Client verhandelt also die neuere Revision. Kein
  Bruch, aber auch kein Protokoll-No-op.

  `PROTOCOL_VERSION` bleibt bei `2025-06-18` — der Guard gegen
  `SUPPORTED_PROTOCOL_VERSIONS` (jetzt `mcp.types.version` statt
  `mcp.shared.version`) hält, der Wert ist also weiter gültig.

- **`_build_mcp()` → `_transport_kwargs()`.** `MCPServer.settings` trägt
  `host`/`port`/`mount_path` nicht mehr; sie sind `run()`-Argumente. Die alte
  Zuweisung ist kein stiller No-op, sondern wirft `ValueError` — ein Test hält
  beides fest, damit der Grund für die Indirektion nicht verloren geht.

  `mount_path` hat in 2.x keine Entsprechung. In 1.x schrieb es nur den
  *angekündigten* Message-Endpoint um, während die Route unpräfixiert blieb —
  korrekt allein dann, wenn eine äussere ASGI-App den Server unter diesem
  Präfix einhängt. 2.x nutzt einen Wert für beides, also bildet
  `SRGSSR_MCP_MOUNT_PATH` auf `message_path` ab, wodurch die Route mitwandert.
  Für `streamable-http` wurde die Einstellung bereits in 1.x ignoriert
  (`run()` gab sie nie an `run_streamable_http_async` weiter); sie bleibt
  ignoriert, denn ein Durchreichen wäre jetzt ein `TypeError` statt eines
  stillen No-ops.

  Geprüft: 156 passed / 14 deselected gegen die 1.x-Baseline von 152 — die
  Differenz sind genau die fünf neuen Tests minus dem einen ersetzten.
  `ruff check src/`, Coverage-Gate (96.7 % gegen 80 %) und ein Install in
  einem frischen venv sind grün.

### Fixed
- **Declared `mcp` explicitly and capped it at `<2`.** This server imports
  `mcp.server.fastmcp`, but never declared `mcp` — it arrived transitively via
  `fastmcp`. `mcp` 2.0.0, published 2026-07-28, removed that module, and the
  only reason installs still work today is an upper bound inside `fastmcp-slim`,
  a package this project never names. The dependency that is actually imported
  is now declared and bounded here rather than left to someone else's resolver.

- **User-Agent no longer reports a stale version.** Three numbers had drifted
  apart: `pyproject.toml` said `1.0.3`, `__init__.__version__` said `0.1.0`, and
  the hard-coded `USER_AGENT` in `_http.py` said `1.0.0`. Every request to the
  SRG SSR APIs carried the stale value. `__version__` now comes from the
  installed distribution metadata (`importlib.metadata`, generated from
  `pyproject.toml`) and the User-Agent is derived from it. Guarded by
  `tests/test_version.py`.

## [1.0.0] – 2026-05-06

Erste stabile Release. Sämtliche Findings des `mcp-audit-skill v0.5.0`-Audits
(`audits/2026-05-05T041445-Z-srgssr-mcp/`) sind adressiert; der Server gilt
als production-ready. Diese Release enthält einen **Breaking Change** beim
Wire-Format der Tool-Returns (SDK-002 Option A — siehe unten); Konsumenten
früherer 0.x-Versionen müssen ihre Parsing-Logik anpassen.

### Changed (BREAKING)
- **Tool Returns (SDK-002, Option A):** **BREAKING CHANGE** — alle 15 Tools und beide Resources liefern jetzt typisierte Pydantic-`BaseModel`-Returns statt Markdown- oder JSON-Strings. Konkret:
  - Neues Modul `src/srgssr_mcp/_models.py` mit `ProvenanceFields`-Mixin (source/license/provenance_url/fetched_at) und 16 Response-Models (`WeatherCurrentResponse`, `EpgProgramsResponse`, `VotationsResponse`, `DailyBriefingResponse`, `ToolErrorResponse`, …)
  - Tool-Signaturen: `-> str` → `-> XYZResponse | ToolErrorResponse`. FastMCP exponiert dadurch automatisch ein `outputSchema` pro Tool im `tools/list`-Manifest, das MCP-Clients für präzise Folge-Calls nutzen können.
  - `response_format`-Field wurde aus allen Input-Models entfernt — JSON ist jetzt das einzige Wire-Format. Markdown-Rendering ist die Aufgabe des Konsumenten (LLM-Clients rendern strukturierte JSON-Daten gut).
  - Resources (`epg://{bu}/{channel_id}/{date}`, `votation://{votation_id}`): mime_type wechselt von `text/markdown` zu `application/json`; Inhalt ist die JSON-Serialisierung des entsprechenden Response-Models.
  - Aggregation (`srgssr_daily_briefing`) returnt `DailyBriefingResponse` mit `weather` und `epg` als typisierte Sub-Responses (jede entweder Erfolgs-Response oder `ToolErrorResponse`); die Graceful-Degradation-Garantie bleibt erhalten.
  - **Migration:** Konsumenten, die Markdown-Output erwarteten, müssen entweder (a) auf JSON umstellen (z.B. `result.model_dump()` in Python, JSON-Parser im LLM-Prompt), oder (b) den alten Markdown-Modus aus früheren Versionen pinnen.
  - Adressiert Audit-Findings SDK-002 (medium, FAIL→PASS) und CH-004 (medium, partial→PASS): Provenance ist jetzt strukturell garantiert auf jedem Return-Pfad inkl. Empty-Result und Error-Cases. `_provenance.py` (alter Footer/Envelope-Helper aus PR #31) wurde entfernt; die provenance lebt jetzt in `_models.py`.

### Security
- **Secret Hygiene (ARCH-005):** `Settings.consumer_key` und `Settings.consumer_secret` sind jetzt als `pydantic.SecretStr` typisiert (vorher `str`) und werden in `repr()` / `str()` / Pydantic-Serialisierung als `**********` maskiert — verhindert akzidentelles Klartext-Leak via Logging. `require_credentials()` unwrappt erst am Boundary via `get_secret_value()`. `.gitignore` erweitert um `.env`, `.env.local`, `.env.*.local`, `secrets/`, `credentials/`, `*.pem`, `*.key`. Neu: `.env.example` als kanonisches Template, `.github/workflows/secret-scan.yml` mit gitleaks. Adressiert Audit-Finding ARCH-005 (critical).
- **DNS-Rebinding-Mitigation (SEC-005):** Process-weiter TTL-Cache (5 min) für DNS-Resolutions in `_validate_url_safe`. Auf dem Hot-Path werden subsequente Aufrufe für denselben Hostnamen ohne erneutes `socket.getaddrinfo` bedient; die cached IP hat bereits die SSRF-Blocklist-Prüfung passiert. Single-source-of-truth-Cache zwischen Validation und (potentiell) Connection-Pooling. Reduziert das duplicate-Resolution-TOCTOU-Fenster, das im Audit-Finding SEC-005 (high) als Hauptanliegen geflaggt war. Volle TOCTOU-Eliminierung erfolgt per Layer-2 (Egress-Proxy via Stripe Smokescreen — siehe neue Sektion in `docs/network-egress.md`).
- **Secret Storage Documentation (SEC-013):** Neue Datei `docs/secret-management.md` dokumentiert den aktuellen Stage-1-Reife (Plain Env-Var) inkl. Akzeptanz-Begründung (Public Open Data, single-tenant, read-only) und Eskalations-Triggern auf Stage 3 (managed Secret Manager) bei Cloud-Deployment, Multi-Tenancy, Write-Pfaden oder PII. `lru_cache(maxsize=1)` auf `get_settings()` durch bounded **5-Minuten-TTL-Cache** ersetzt — rotierte Upstream-Credentials werden jetzt innerhalb von 300 s aktiv statt erst beim Process-Restart. Adressiert Audit-Finding SEC-013 (high).
- **Egress-Allowlist-Dokumentation (SEC-021):** Die Code-Layer-Egress-Allowlist (`ALLOWED_HOSTS = {"api.srgssr.ch"}` in `_http.py`, gemeinsam mit SEC-004 SSRF-Defense bereits implementiert) ist jetzt explizit in `README.md` und `README.de.md` als eigener «Security: Egress Allowlist» / «Sicherheit: Egress-Allowlist»-Abschnitt dokumentiert (Allowed Hosts, Erweiterungsprozedur, Pointer auf Tests). Neue Datei `docs/network-egress.md` beschreibt den Network-Layer-Defense-in-Depth-Plan (Kubernetes NetworkPolicy mit FQDN-Egress via Cilium, AWS Security Group, Cloudflare WARP Zero Trust) für zukünftige `sse`/`streamable-http`-Deployments — für den aktuellen `stdio`-Transport nicht anwendbar (Prozess läuft im User-Kontext des MCP-Clients). Neues Audit-Finding `audits/2026-04-30-srgssr-mcp/findings/SEC-021-egress-allowlist.md` dokumentiert den `resolved`-Status mit Test-Matrix.
- **Input Validation Hardening (SEC-018):** Alle 10 Pydantic-Tool-Input-Models (`EpgProgramsInput`, `AudioEpisodesInput`, `PolisListInput`, `PolisResultInput`, `VideoShowsInput`, `VideoEpisodesInput`, `VideoLivestreamsInput`, `WeatherSearchInput`, `WeatherForecastInput`, `DailyBriefingInput`) laufen jetzt im Pydantic-`strict`-Mode (keine implizite Type-Coercion `"5"` → `5`); `extra="forbid"` war bereits vorhanden. Zusätzlich wurden Pattern-Constraints für alle freien String-Felder ergänzt: `channel_id`, `show_id`, `votation_id`, `geolocation_id` akzeptieren nur `^[A-Za-z0-9_-]+$` (blockiert Path-Traversal, URL-Injection, SQL-Metacharacter, Whitespace), `canton` nur `^[A-Za-z]{2,4}$`, `query` (Wettersuche) nur `^[\w\s.\-']+$` (Unicode-aware, blockiert HTML/Script-Payloads). Verteidigt gegen Tool-Boundary-Injection-Angriffe via MCP-Inputs. 23 neue Unit-Tests in `tests/test_unit.py` decken Strict-Mode-Enforcement, Extra-Field-Rejection und alle Pattern-Constraints ab.
- **SSRF Defense (SEC-004 + SEC-021):** Jeder ausgehende HTTP-Request in `_http.py` durchläuft jetzt `_validate_url_safe()` und wird blockiert, wenn (a) das Schema nicht `https` ist, (b) der Hostname nicht in `ALLOWED_HOSTS = {"api.srgssr.ch"}` (Egress-Allowlist) liegt, oder (c) eine der vom Hostname aufgelösten IPs in einer der gesperrten Ranges fällt (RFC1918 privat, Loopback, Link-Local inkl. `169.254.169.254` Cloud-Metadata, CGNAT, Multicast, Reserved sowie die IPv6-Pendants ULA/Link-Local/Loopback/Mapped). Defense-in-Depth gegen DNS-Rebinding und gegen zukünftige Code-Pfade, die URLs aus weniger vertrauenswürdiger Eingabe konstruieren. Aufrufstellen sind `_get_access_token` (OAuth-Token-Endpoint) und `_api_get` (alle Tool-Calls). Verstöße werden als `ValueError` propagiert und durch `_handle_error` zu `Konfigurationsfehler: …` lokalisiert, sodass keine internen Netz-Details an den MCP-Client gelangen. 20 neue Unit-Tests in `tests/test_unit.py` decken HTTPS-Enforcement, Allowlist, alle blockierten IP-Kategorien (inkl. IPv6 und gemischter A/AAAA-Antworten), DNS-Resolver-Fehler und die Integration in `_api_get` / `_safe_api_get` ab.

### Added
- **Lifespan + Connection Pooling (SDK-001):** Neuer `@asynccontextmanager`-Lifespan in `_app.py` ownt einen Process-weit geteilten `httpx.AsyncClient`. `_api_get` und `_get_access_token` nutzen den shared Client (vorher: pro Tool-Call ein neuer `async with httpx.AsyncClient(…)`). Das schaltet HTTP-Connection-Pooling an — kein TCP-Handshake plus TLS-Setup pro Request mehr — und schliesst den Resource-Lifecycle sauber ab beim Server-Shutdown. `asyncio.Lock` schützt erste Client-Erzeugung gegen Race bei `asyncio.gather`-Fan-out, ebenso die initiale OAuth-Token-Refresh-Race. Adressiert Audit-Finding SDK-001 (high, FAIL→PASS) — war der Production-Blocker.
- **Context Injection (SDK-003):** Alle 15 Tools haben jetzt einen optionalen `ctx: Context | None = None`-Parameter. Tools emittieren `await ctx.info(...)` bei Invocation und `srgssr_daily_briefing` zusätzlich `await ctx.report_progress(0/2)` bzw. `(2/2)` um den `asyncio.gather`-Fan-out — MCP-Clients sehen während der Cross-Domain-Aggregation Lebenszeichen. Default ist `None`, daher non-breaking für direkte Funktionsaufrufe (z.B. Tests). Adressiert Audit-Finding SDK-003 (medium, FAIL→PASS).
- **Error Hardening (OBS-001 / OBS-002):** Default-Fallback in `_handle_error()` gibt nicht mehr `str(e)` durch — interne Hostnames, IP-Adressen oder Socket-Details (`gaierror`) bleiben jetzt im strukturierten Server-Log via `logger.error(..., exc_info=e)` und erreichen den LLM-Client nicht mehr. Verhindert Information-Disclosure bei unerwarteten Exceptions. Adressiert Audit-Findings OBS-001 (high) und OBS-002 (high).
- **Docs (OPS-003):** Neue README-Sektion «Development Phase» / «Entwicklungsphase» (EN/DE) deklariert den Server explizit als **Phase 1: Read-only Wrapper** und listet die Phase-1-Abschlusskriterien als Checkliste (14 Tools, OAuth2, bilinguale Doku, Test-Suite via OPS-001, Structured Logging via OBS-003; ausstehend: Production-ready Error-Handling). Phase 2 (Write) ist als *nicht geplant* markiert — die SRG SSR APIs sind per Vertrag read-only. Phase 3 (Multi-Agent) wird auf User-Feedback-getriebene Re-Evaluation aufgeschoben.
- **Observability (OBS-003):** Structured logging via `structlog` mit JSON-Output auf stderr und RFC-5424-Severity-Stufen (debug/info/notice/warning/error/critical/alert/emergency). Jeder Tool-/Resource-Aufruf bindet Kontext (`tool`, `business_unit`, `channel_id`, `query`, …) und emittiert `tool_invoked`/`tool_succeeded`/`tool_failed`-Events; OAuth-Token-Refresh und Server-Lifecycle werden ebenfalls geloggt. Stdio-Transport bleibt sauber (stdout für JSON-RPC, Logs auf stderr). Konfiguration via `SRGSSR_LOG_LEVEL` (Default `info`). Neue `tests/test_logging.py` mit 9 Tests; neue Dependency `structlog>=24.1.0`.

### Changed
- **Architecture (ARCH-012):** **MCP `protocolVersion` pinned to `2025-06-18`** (vorher SDK-Default). Die Spec-Version ist als `PROTOCOL_VERSION`-Konstante in `src/srgssr_mcp/_app.py` explizit verankert und wird beim Import gegen die `SUPPORTED_PROTOCOL_VERSIONS` des installierten MCP-SDK validiert — ein SDK-Upgrade, das die gepinnte Spec-Revision nicht mehr unterstützt, schlägt sofort beim Start fehl statt still die Wire-Semantik zu ändern. README erhält eine «MCP Protocol Version»-Sektion mit Update-Policy; Dependabot wartet die `mcp`/`fastmcp`-Dependencies monatlich.
- **Architecture (ARCH-011):** `server.py` (~1900 Zeilen) wurde in fokussierte Module aufgeteilt: `config.py` (Settings), `_http.py` (OAuth/HTTP-Plumbing), `_app.py` (FastMCP-Instanz + Enums) sowie `tools/{weather,video,audio,epg,polis,aggregation,resources,prompts}.py` mit jeweils einem Tool-Cluster. `server.py` ist jetzt ein dünner Entry-Point, der die Tool-Module zur Registrierung importiert und alle bestehenden Symbole für Rückwärtskompatibilität re-exportiert. Public API (`from srgssr_mcp.server import …`) bleibt unverändert; alle 78 Unit-Tests passieren weiter.

### Added
- **Architecture (ARCH-008):** Server nutzt jetzt alle drei MCP-Primitive. Neue **Resources** mit URI-Templates für stabile, cache-freundliche Daten: `epg://{bu}/{channel_id}/{date}` für EPG-Tagesprogramme (SRF/RTS/RSI) und `votation://{votation_id}` für abgeschlossene Schweizer Volksabstimmungen. Neue **Prompts** für wiederkehrende Workflows: `analyse_abstimmungsverhalten` (Stadt-Land/Sprachregionen/Kantone-Fokus) und `tagesbriefing_kanton` (Wetter + EPG für eine Stadt). Tools bleiben für parametrisierte Suchen erhalten.

### Changed
- **Architecture (ARCH-004):** Konfiguration wurde auf Pydantic `BaseSettings` umgestellt (`srgssr_mcp.server.Settings`). Credentials und Transport (`stdio` / `sse` / `streamable-http`) werden zentral aus Environment-Variablen gelesen (`SRGSSR_CONSUMER_KEY`, `SRGSSR_CONSUMER_SECRET`, `SRGSSR_MCP_TRANSPORT`, `SRGSSR_MCP_HOST`, `SRGSSR_MCP_PORT`, `SRGSSR_MCP_MOUNT_PATH`). `main()` wählt den Transport zur Laufzeit; Tools bleiben transport-agnostisch.
- **UX (ARCH-003):** `srgssr_weather_search_location` führt bei leerem Resultat automatische Retries mit normalisierten Query-Varianten (ASCII-gefaltet, lowercase) aus — «Zurich» trifft jetzt «Zürich». Bei finaler Leere werden versuchte Varianten und Suggestions (PLZ, Diakritika) zurückgegeben.
- **UX (ARCH-003):** 404-Antworten in ID-Lookup-Tools (`srgssr_video_get_episodes`, `srgssr_audio_get_episodes`, `srgssr_polis_get_votation_results`, `srgssr_epg_get_programs`) verweisen jetzt auf das passende Listing-Tool zur ID-Auflösung.
- **UX (ARCH-003):** Listen-Tools (`srgssr_video_get_shows`, `srgssr_audio_get_shows`, beide Livestream-Tools, `srgssr_polis_get_votations`, `srgssr_polis_get_elections`) liefern bei leerem Resultat strukturierte Vorschläge (alternative Business Units, Filter lockern).
- **Docs (OPS-002):** Architecture-Diagramm in README.md/README.de.md auf Tool-Cluster-Layout (Weather/EPG/Polis/Video/Audio) umgestellt
- **Docs (OPS-002):** «Known Limits» / «Bekannte Limits» Sektion ergänzt um Rate Limits, Data Freshness (EPG ≤ 6h Verzögerung), Historical Data (Polis ab 1900) und Geo-Restriction

## [0.1.0] - 2026-03-29

### Added
- Initial release
- 12 Tools für SRG SSR APIs: SRF Wetter (4), Video (3), Audio (3), EPG (1), Polis/Demokratie (3)
- Unterstützung für SRF, RTS, RSI, RTR, SWI
- Historische Abstimmungs- und Wahldaten seit 1900 via Polis-API
- OAuth2-Authentifizierung für SRG SSR Developer APIs
- Dual-Transport: stdio (lokal) + Streamable HTTP (Cloud)

## [0.1.0] – 2026-03-29

### Neu
- **14 Tools** in 5 thematischen Clustern
- **Wetter (4):** `srgssr_weather_search_location`, `srgssr_weather_current`, `srgssr_weather_forecast_24h`, `srgssr_weather_forecast_7day`
- **Video (3):** `srgssr_video_get_shows`, `srgssr_video_get_episodes`, `srgssr_video_get_livestreams`
- **Audio (3):** `srgssr_audio_get_shows`, `srgssr_audio_get_episodes`, `srgssr_audio_get_livestreams`
- **EPG (1):** `srgssr_epg_get_programs`
- **Polis (3):** `srgssr_polis_get_votations`, `srgssr_polis_get_votation_results`, `srgssr_polis_get_elections`
- Unterstützung für alle SRG SSR Unternehmenseinheiten: SRF, RTS, RSI, RTR, SWI
- Historische Abstimmungs- und Wahldaten seit 1900 via Polis-API
- OAuth2 Client Credentials mit automatischem Token-Caching
- Duale Transport-Unterstützung: stdio (lokal) und Streamable HTTP (Cloud)
- Paginierungsunterstützung für alle Listen-Tools
- GitHub Actions CI für Python 3.11–3.13
- Bilinguales README (DE/EN) und CONTRIBUTING (DE/EN)

### Quellen
- SRG SSR PUBLIC API V2 via [developer.srgssr.ch](https://developer.srgssr.ch)
