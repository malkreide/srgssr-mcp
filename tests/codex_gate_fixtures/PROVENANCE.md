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

**Quelle:** `malkreide/srgssr-mcp` PR #119, Kommentar-ID 5726220512
**Aufgenommen:** 2026-09-18, 06:40:13 UTC (`created_at` == `updated_at`)

Bis zum 18.9.2026 stand hier ein **Zitat** aus `CLAUDE.md` mit gesetzten IDs und
Zeitstempeln, ausdruecklich als schwaechste der Aufzeichnungen benannt — die
Meldung war in diesem Repo nie beobachtet worden. Jetzt ist sie es, und der
Unterschied ist nicht bloss formal: der echte Koerper traegt einen zweiten Satz
mit Link aufs Usage-Dashboard, den die August-Fassung nicht hatte.

Das Suchmuster des Gates (`reached your Codex usage limits`) greift bei beiden.
Genau dafuer ist es kurz gehalten — ein Muster, das den ganzen Satz verlangt
haette, waere an dieser Drift gescheitert, ohne dass jemand es merkt.

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
