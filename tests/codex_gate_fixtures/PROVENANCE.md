# Aufgezeichnete Codex-Kommentare

Rohe JSON-Antworten von `repos/{owner}/{repo}/issues/{n}/comments`, gegen die
`tests/test_codex_gate.py` das **echte** Skript aus
`.github/workflows/codex-gate.yml` faehrt — mit dem `--jq`-Ausdruck des
Workflows, nicht an ihm vorbei.

Warum roh und nicht fertig gefiltert: die erste Fassung legte die reinen
Kommentartexte hin und nahm dem Skript damit die Arbeit ab, um die es geht. Ein
fehlender Autorenfilter war so nicht zu bemerken. `user.login` gehoert deshalb
in jede Aufzeichnung.

Warum aufgezeichnet und nicht erfunden: ein selbst geschriebener Beispieltext
haette genau die Form, die der Parser erwartet, und koennte ihn deshalb nicht
widerlegen.

## `running.json`, `completed.json`

**Quelle:** `malkreide/srgssr-mcp` PR #116, Kommentar-ID 5724943260
**Aufgenommen:** 2026-09-18 — Zustand `Running` um 03:59:31 UTC (`created_at`),
Zustand `Completed` um 04:00:35 UTC (`updated_at`)

Dieselbe Kommentar-ID in beiden Dateien: die Statustabelle wird an Ort und
Stelle ueberschrieben. Genau diese Ueberschreibung ist der Grund, warum das Gate
in einer Schleife liest statt einmal — ein einmal gelesener Text ist kein Beleg.

## `environment.json`

**Quelle:** `malkreide/srgssr-mcp` PR #117, Kommentar-ID 5725034944
**Aufgenommen:** 2026-09-18, 04:12:00 UTC (`created_at` == `updated_at`)

Der Koerper woertlich, mit dem Link, den die Fassung in `CLAUDE.md` nicht hatte.
Die Meldung kam elf Sekunden nach dem Eroeffnen von #117 — als Draft —, und
elf Minuten nachdem #116 im selben Repo einen vollstaendigen Review bekommen
hatte. Sie ist damit **kein** Beleg fuer eine fehlende Environment; siehe
`CLAUDE.md`, «Die Environment-Meldung ist kein Befund».

## `kontingent.json`

**Quelle:** der Text woertlich aus `CLAUDE.md` Teil 1, wo er am 21.–23.8.2026 in
`malkreide/*-mcp` aufgezeichnet wurde. **In diesem Repo nicht beobachtet** —
deshalb ein Zitat und keine eigene Messung. Autor, IDs und Zeitstempel sind hier
gesetzt, nicht aufgenommen; das ist die schwaechste der Aufzeichnungen und steht
hier so benannt.

## Zusammengesetzt aus den obigen

Die Faelle, um die es nach dem Umbau vom 18.9.2026 geht, brauchen **zwei**
Kommentare im selben Thread. Sie sind aus den Aufzeichnungen oben
zusammengesetzt, nicht neu geschrieben:

- **`draft_meldung_dann_laufender_review.json`** — die Draft-Meldung aus #117
  und die laufende Tabelle aus #116. Das ist die Lage, die #117 nach dem
  Ready-Klick gehabt haette. Die erste Fassung des Gates liess hier sofort
  durch.
- **`draft_meldung_dann_abgeschlossen.json`** — dieselbe Meldung mit der
  abgeschlossenen Tabelle. Gegenrichtung: das Gate muss trotz der Meldung
  normal und **sofort** oeffnen.
- **`mensch_zitiert_ausfalltext.json`** — ein menschlicher Kommentar, der einen
  Ausfalltext zitiert, plus die laufende Tabelle. Der Kommentartext ist hier
  geschrieben und nicht aufgezeichnet; aufgezeichnet ist, was zaehlt — der
  `user.login` eines Menschen gegen den des Bots.
