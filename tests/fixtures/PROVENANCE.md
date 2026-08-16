# Herkunft der Fixtures

Aufgezeichnet am **2026-08-16** mit `PYTHONPATH=src python scripts/record_fixtures.py`.

Eine Antwort je **Abfrage**, nicht je Endpunkt: `srgssr_weather_search_location`
faechert ueber `_query_variants` in mehrere Suchen auf, `srgssr_daily_briefing`
spannt EPG und Wetter zugleich, und drei Werkzeuge holen sich vorher eine ID.
Fuenf Dateien wuerden die Portfolio-Regel erfuellen und fast nichts belegen.

Der **Schluessel** unten ist, woran der Test eine Anfrage wiedererkennt: die
volle URL samt Query. Zugeordnet wird nach der Anfrage und nicht nach der
Reihenfolge — `srgssr_daily_briefing` ruft nebenlaeufig ab, und die Reihenfolge,
in der die Antworten zurueckkommen, ist keine Zusicherung.

Die Antworten stammen aus dem geteilten Client von `_http._get_http_client()`
(gleicher User-Agent, gleiches Timeout, gleiche Retry-Mechanik wie im Betrieb),
abgegriffen ueber einen httpx-Response-Hook. Ausgeloest hat sie jeweils das
Werkzeug selbst — so belegt die Aufzeichnung auch, dass das Werkzeug genau
diese Anfrage schickt.

## Kein Token, keine Header

Die Antwort von `/oauth/v1/accesstoken` traegt ein gueltiges Bearer-Token und
wird nie abgelegt; ihre URL taucht auch als Schluessel nicht auf. Abgelegt sind
ausschliesslich Antwort-Rumpfe — kein Header der Anfrage (dort steht
`Authorization: Basic <key:secret>`) und keiner der Antwort. Vor dem Schreiben
prueft der Recorder jede Datei und jeden Schluessel gegen Token, Key und Secret
und bricht ab, statt zu warnen.

## Auswahl

Neu gesetzt ist die Einrueckung; gekuerzt ist allein die **Zahl** der
Listeneintraege. Kein Feld eines behaltenen Eintrags ist angetastet, und
Zaehlfelder daneben stehen wie geliefert.

Wo der Server *in* einer Liste filtert, gruppiert oder zaehlt — Polis und das
Tagesbriefing —, wird nicht gekuerzt: ein Schnitt erfaende dort einen
Negativbefund, der wie ein Ergebnis aussieht.

Die Fehlerpfade — Timeout, 5xx, 401, ein Gateway-Redirect — bleiben
handgeschrieben. Sie lassen sich nicht auf Zuruf aufzeichnen und sind als
Erfindung in Ordnung.

## `audio_episodes_1.json`

- **Werkzeuge:** `srgssr_audio_get_episodes`
- **Schluessel:** `https://api.srgssr.ch/audiometadata/v2/episodeComposition/shows/d6dc9051-df9b-474d-948c-54c68d18e648?bu=srf&pageSize=3`
- **Auswahl:** ungekuerzt
- **Groesse:** 9703 Bytes
- **SHA-256:** `1cd15a9fcfd64581f90198f712c3596ded11519fb3df5b59da71755e592eb368`

## `audio_livestreams_1.json`

- **Werkzeuge:** `srgssr_audio_get_livestreams`
- **Schluessel:** `https://api.srgssr.ch/audiometadata/v2/radio/channels?bu=srf`
- **Auswahl:** 3 von 6 Listeneintraegen — jede Liste im Baum auf die ersten 3 gekuerzt, aus 2306 Bytes Rohantwort
- **Groesse:** 1376 Bytes
- **SHA-256:** `2f50d61ad3d69796149ae428f828ee0247c7a3573166051c9f96a6159b563578`

## `audio_shows_1.json`

- **Werkzeuge:** `srgssr_audio_get_shows`
- **Schluessel:** `https://api.srgssr.ch/audiometadata/v2/radioshows/byChannel?bu=srf&channelId=69e8ac16-4327-4af4-b873-fd5cd6e895a7&characterFilter=e&pageSize=5`
- **Auswahl:** 13 von 15 Listeneintraegen — jede Liste im Baum auf die ersten 3 gekuerzt, aus 10386 Bytes Rohantwort
- **Groesse:** 7363 Bytes
- **SHA-256:** `ac1cb6a538829749146dd042fe86554826c5667c2a775b2edc70e9ce4837c1ef`

## `daily_briefing_1.json`

- **Werkzeuge:** `srgssr_daily_briefing`
- **Schluessel:** `https://api.srgssr.ch/srf-meteo/v2/geolocations?latitude=47.3700&longitude=8.5400`
- **Notiz:** Spannt EPG und Wetter nebenlaeufig — zwei Produkte in einem Aufruf.
- **Auswahl:** ungekuerzt
- **Groesse:** 771 Bytes
- **SHA-256:** `3000d35e31be7976bba4381445a19b0e113363ab33754fa12f813faec105d952`

## `epg_programs_1.json`

- **Werkzeuge:** `srgssr_daily_briefing`, `srgssr_epg_get_programs`
- **Schluessel:** `https://api.srgssr.ch/epg/v3/srf/tv/stations/srf-1?date=2026-08-15`
- **Auswahl:** 17 von 56 Listeneintraegen — jede Liste im Baum auf die ersten 3 gekuerzt, aus 163032 Bytes Rohantwort
- **Groesse:** 14466 Bytes
- **SHA-256:** `5e82dd1b9352f21ba0608d5c2e05df5fb1f5ebd7730ee49b194a24f05cc2c4ec`

## `polis_elections_1.json`

- **Werkzeuge:** `srgssr_polis_get_elections`
- **Schluessel:** `https://api.srgssr.ch/polis-api/v2/elections?lang=de&caseid=1623`
- **Auswahl:** 43 von 56 Listeneintraegen — jede Liste im Baum auf die ersten 3 gekuerzt, aus 12628 Bytes Rohantwort
- **Geschuetzte Liste:** `Election` behaelt alle Eintraege — wie bei den Abstimmungen; die Liste haengt hier eine Ebene tiefer unter `Elections`
- **Groesse:** 25932 Bytes
- **SHA-256:** `7e379484d6e3126be0dfc8c4d91fd0e3cf1eebb0664a28164a1bb2685b44af38`

## `polis_elections_2.json`

- **Werkzeuge:** `srgssr_polis_get_elections`
- **Schluessel:** `https://api.srgssr.ch/polis-api/v2/elections?lang=de&caseid=1625`
- **Auswahl:** 31 von 48 Listeneintraegen — jede Liste im Baum auf die ersten 3 gekuerzt, aus 16145 Bytes Rohantwort
- **Geschuetzte Liste:** `Election` behaelt alle Eintraege — wie bei den Abstimmungen; die Liste haengt hier eine Ebene tiefer unter `Elections`
- **Groesse:** 17411 Bytes
- **SHA-256:** `95a7187161ace1537cb7681052c08d98137d8234f74d6a2c5d556754d7927a12`

## `polis_elections_3.json`

- **Werkzeuge:** `srgssr_polis_get_elections`
- **Schluessel:** `https://api.srgssr.ch/polis-api/v2/elections?lang=de&caseid=1621`
- **Auswahl:** ungekuerzt
- **Geschuetzte Liste:** `Election` behaelt alle Eintraege — wie bei den Abstimmungen; die Liste haengt hier eine Ebene tiefer unter `Elections`
- **Groesse:** 39 Bytes
- **SHA-256:** `e56862ae80c23e4985f8bcc7282e24661844a5b9d6571ae1c32b1ea1f4b8fd33`

## `polis_elections_4.json`

- **Werkzeuge:** `srgssr_polis_get_elections`
- **Schluessel:** `https://api.srgssr.ch/polis-api/v2/elections?lang=de&caseid=1616`
- **Auswahl:** 36 von 52 Listeneintraegen — jede Liste im Baum auf die ersten 3 gekuerzt, aus 13289 Bytes Rohantwort
- **Geschuetzte Liste:** `Election` behaelt alle Eintraege — wie bei den Abstimmungen; die Liste haengt hier eine Ebene tiefer unter `Elections`
- **Groesse:** 18685 Bytes
- **SHA-256:** `8fc189a8d0449ec11ea88b08f8e921135a8d168e2031cb0bda91167c4edef48b`

## `polis_elections_5.json`

- **Werkzeuge:** `srgssr_polis_get_elections`
- **Schluessel:** `https://api.srgssr.ch/polis-api/v2/elections?lang=de&caseid=1617`
- **Auswahl:** 31 von 44 Listeneintraegen — jede Liste im Baum auf die ersten 3 gekuerzt, aus 8468 Bytes Rohantwort
- **Geschuetzte Liste:** `Election` behaelt alle Eintraege — wie bei den Abstimmungen; die Liste haengt hier eine Ebene tiefer unter `Elections`
- **Groesse:** 17052 Bytes
- **SHA-256:** `e2a57a9a18473e2c6a6472025e962fc242834f7c798afc47c7314de625c9f1ed`

## `polis_elections_6.json`

- **Werkzeuge:** `srgssr_polis_get_elections`
- **Schluessel:** `https://api.srgssr.ch/polis-api/v2/elections?lang=de&caseid=1613`
- **Auswahl:** 27 von 40 Listeneintraegen — jede Liste im Baum auf die ersten 3 gekuerzt, aus 6594 Bytes Rohantwort
- **Geschuetzte Liste:** `Election` behaelt alle Eintraege — wie bei den Abstimmungen; die Liste haengt hier eine Ebene tiefer unter `Elections`
- **Groesse:** 12868 Bytes
- **SHA-256:** `0fe5fcbc4a6008fac656cdab96f8bc88eb9abb608c2e388d0fc149a65374600f`

## `polis_elections_7.json`

- **Werkzeuge:** `srgssr_polis_get_elections`
- **Schluessel:** `https://api.srgssr.ch/polis-api/v2/elections?lang=de&caseid=1609`
- **Auswahl:** 42 von 55 Listeneintraegen — jede Liste im Baum auf die ersten 3 gekuerzt, aus 11164 Bytes Rohantwort
- **Geschuetzte Liste:** `Election` behaelt alle Eintraege — wie bei den Abstimmungen; die Liste haengt hier eine Ebene tiefer unter `Elections`
- **Groesse:** 22781 Bytes
- **SHA-256:** `db322892271a7b3f8eb8d9966da27f696cb9cbd6144c6f8c8f0b0eac885bcf0c`

## `polis_elections_8.json`

- **Werkzeuge:** `srgssr_polis_get_elections`
- **Schluessel:** `https://api.srgssr.ch/polis-api/v2/elections?lang=de&caseid=1608`
- **Auswahl:** 70 von 112 Listeneintraegen — jede Liste im Baum auf die ersten 3 gekuerzt, aus 74652 Bytes Rohantwort
- **Geschuetzte Liste:** `Election` behaelt alle Eintraege — wie bei den Abstimmungen; die Liste haengt hier eine Ebene tiefer unter `Elections`
- **Groesse:** 47278 Bytes
- **SHA-256:** `1d1e786b55cf73636e56ba055f22ea33ef357df2915f4d74f76622ae7df1fcac`

## `polis_results_1.json`

- **Werkzeuge:** `srgssr_polis_get_votation_results`
- **Schluessel:** `https://api.srgssr.ch/polis-api/v2/votations/1627?lang=de`
- **Auswahl:** ungekuerzt
- **Geschuetzte Liste:** `Items` behaelt alle Eintraege — `_fetch_filtered` zaehlt die Treffer ueber mehrere Faelle hinweg bis `page * page_size` — ein Schnitt verschiebt, welche Faelle beitragen
- **Groesse:** 1124 Bytes
- **SHA-256:** `f66051b7b3f5bdab5361c9c563b3b8cf0009bf87d4b1101f39bc44dbdd166867`

## `polis_votations_1.json`

- **Werkzeuge:** `srgssr_polis_get_elections`, `srgssr_polis_get_votations`
- **Schluessel:** `https://api.srgssr.ch/polis-api/v2/cases?lang=de&listAllCases=true`
- **Auswahl:** 1873 von 4494 Listeneintraegen — jede Liste im Baum auf die ersten 3 gekuerzt, aus 1489589 Bytes Rohantwort
- **Geschuetzte Liste:** `Case` behaelt alle Eintraege — `_case_ids_in_range` filtert *in* dieser Liste nach Jahr — ein Schnitt meldete «keine Abstimmung in diesem Zeitraum», wo es welche gibt
- **Groesse:** 997917 Bytes
- **SHA-256:** `df275677a1e0c494da96daac0835b493c7633e058222fbbf60d16faf14ab56b5`

## `polis_votations_2.json`

- **Werkzeuge:** `srgssr_polis_get_votations`
- **Schluessel:** `https://api.srgssr.ch/polis-api/v2/votations?lang=de&caseid=1626`
- **Auswahl:** ungekuerzt
- **Geschuetzte Liste:** `Items` behaelt alle Eintraege — `_fetch_filtered` zaehlt die Treffer ueber mehrere Faelle hinweg bis `page * page_size` — ein Schnitt verschiebt, welche Faelle beitragen
- **Groesse:** 54 Bytes
- **SHA-256:** `05947b5cbcb0567e85c6ac543e067a5465bef6d84dc82842c434091e7b100d2d`

## `polis_votations_3.json`

- **Werkzeuge:** `srgssr_polis_get_votations`
- **Schluessel:** `https://api.srgssr.ch/polis-api/v2/votations?lang=de&caseid=1627`
- **Auswahl:** 215 von 10367 Listeneintraegen — jede Liste im Baum auf die ersten 3 gekuerzt, aus 4464747 Bytes Rohantwort
- **Geschuetzte Liste:** `Items` behaelt alle Eintraege — `_fetch_filtered` zaehlt die Treffer ueber mehrere Faelle hinweg bis `page * page_size` — ein Schnitt verschiebt, welche Faelle beitragen
- **Groesse:** 146648 Bytes
- **SHA-256:** `2fb2fcd1b620a9416dcc1f0d25539058624b6dca43a9cc84b9045c9a13d457f9`

## `polis_votations_4.json`

- **Werkzeuge:** `srgssr_polis_get_votations`
- **Schluessel:** `https://api.srgssr.ch/polis-api/v2/votations?lang=de&caseid=1623`
- **Auswahl:** ungekuerzt
- **Geschuetzte Liste:** `Items` behaelt alle Eintraege — `_fetch_filtered` zaehlt die Treffer ueber mehrere Faelle hinweg bis `page * page_size` — ein Schnitt verschiebt, welche Faelle beitragen
- **Groesse:** 54 Bytes
- **SHA-256:** `05947b5cbcb0567e85c6ac543e067a5465bef6d84dc82842c434091e7b100d2d`

## `polis_votations_5.json`

- **Werkzeuge:** `srgssr_polis_get_votations`
- **Schluessel:** `https://api.srgssr.ch/polis-api/v2/votations?lang=de&caseid=1625`
- **Auswahl:** ungekuerzt
- **Geschuetzte Liste:** `Items` behaelt alle Eintraege — `_fetch_filtered` zaehlt die Treffer ueber mehrere Faelle hinweg bis `page * page_size` — ein Schnitt verschiebt, welche Faelle beitragen
- **Groesse:** 4188 Bytes
- **SHA-256:** `00ebc2bbbeb942399fcb59f9eba9b4e1a850e4161915789ea3e009699621c3fc`

## `polis_votations_6.json`

- **Werkzeuge:** `srgssr_polis_get_votations`
- **Schluessel:** `https://api.srgssr.ch/polis-api/v2/votations?lang=de&caseid=1624`
- **Auswahl:** 106 von 4666 Listeneintraegen — jede Liste im Baum auf die ersten 3 gekuerzt, aus 2004894 Bytes Rohantwort
- **Geschuetzte Liste:** `Items` behaelt alle Eintraege — `_fetch_filtered` zaehlt die Treffer ueber mehrere Faelle hinweg bis `page * page_size` — ein Schnitt verschiebt, welche Faelle beitragen
- **Groesse:** 66199 Bytes
- **SHA-256:** `c96b11211482ac29d4cffecdebcc0b9a428f8df995ed86608f3eaba6969c6f63`

## `video_episodes_1.json`

- **Werkzeuge:** `srgssr_video_get_episodes`
- **Schluessel:** `https://api.srgssr.ch/videometadata/v2/latest_episodes/shows/ff969c14-c5a7-44ab-ab72-14d4c9e427a9?bu=srf&pageSize=3`
- **Auswahl:** 32 von 44 Listeneintraegen — jede Liste im Baum auf die ersten 3 gekuerzt, aus 31133 Bytes Rohantwort
- **Groesse:** 18326 Bytes
- **SHA-256:** `49972fdba326fcd79e6dbb578af32b0979d340e66940f3dbf5e8b8b689101592`

## `video_livestreams_1.json`

- **Werkzeuge:** `srgssr_video_get_livestreams`
- **Schluessel:** `https://api.srgssr.ch/videometadata/v2/tv_channels?bu=srf`
- **Auswahl:** ungekuerzt
- **Groesse:** 1325 Bytes
- **SHA-256:** `df0c0e1fcca15b72621ab7d79f233e9bde3baf1f107d1663f5691f8c00fe43e0`

## `video_shows_1.json`

- **Werkzeuge:** `srgssr_video_get_shows`
- **Schluessel:** `https://api.srgssr.ch/videometadata/v2/tv_shows/alphabetical?bu=srf&characterFilter=t&pageSize=5`
- **Auswahl:** 7 von 9 Listeneintraegen — jede Liste im Baum auf die ersten 3 gekuerzt, aus 9342 Bytes Rohantwort
- **Groesse:** 6836 Bytes
- **SHA-256:** `e38cfb735965ed2b3838af6427ac4ed5e6a78a75010a69f1e48d6bd3f17c72ce`

## `weather_current_1.json`

- **Werkzeuge:** `srgssr_weather_current`, `srgssr_weather_forecast_24h`, `srgssr_weather_forecast_7day`
- **Schluessel:** `https://api.srgssr.ch/srf-meteo/v2/geolocations?latitude=47.3769&longitude=8.5417`
- **Auswahl:** 4 von 5 Listeneintraegen — jede Liste im Baum auf die ersten 3 gekuerzt, aus 1518 Bytes Rohantwort
- **Groesse:** 1671 Bytes
- **SHA-256:** `345d622e591c46a9b63f958e87aafbcc302640c231cf10aa4abcc5625ceda01a`

## `weather_current_2.json`

- **Werkzeuge:** `srgssr_weather_current`, `srgssr_weather_forecast_24h`, `srgssr_weather_forecast_7day`
- **Schluessel:** `https://api.srgssr.ch/srf-meteo/v2/forecastpoint/47.3797,8.5342`
- **Auswahl:** 12 von 156 Listeneintraegen — jede Liste im Baum auf die ersten 3 gekuerzt, aus 61210 Bytes Rohantwort
- **Groesse:** 7186 Bytes
- **SHA-256:** `12b76f1dc5d59138d048a3393b65315d2154789dc7c227623568140706fd9c1c`

## `weather_search_1.json`

- **Werkzeuge:** `srgssr_weather_search_location`
- **Schluessel:** `https://api.srgssr.ch/srf-meteo/v2/geolocationNames?name=Z%C3%BCrich&limit=10`
- **Notiz:** Faechert ueber `_query_variants` auf — mehrere Suchen je Aufruf.
- **Auswahl:** 6 von 8 Listeneintraegen — jede Liste im Baum auf die ersten 3 gekuerzt, aus 3784 Bytes Rohantwort
- **Groesse:** 3645 Bytes
- **SHA-256:** `20f730281dfb5a767561b783c1a4434492532f449a5dce1195e19eedb5385cf8`
