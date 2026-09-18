# Aufgezeichnete Codex-Kommentare

Woertliche Koerper von Issue-Kommentaren des `chatgpt-codex-connector[bot]`,
gegen die `tests/test_codex_gate.py` das **echte** Skript aus
`.github/workflows/codex-gate.yml` faehrt.

Warum aufgezeichnet und nicht erfunden: ein selbst geschriebener Beispieltext
haette genau die Form, die der Parser erwartet, und koennte ihn deshalb nicht
widerlegen. Diese hier sind das, was Codex wirklich geschickt hat.

## `running.txt`

**Quelle:** `malkreide/srgssr-mcp` PR #116, Kommentar-ID 5724943260
**Aufgenommen:** 2026-09-18, Zustand um 03:59:31 UTC (`created_at`)

## `completed.txt`

**Quelle:** dieselbe Kommentar-ID 5724943260 — die Statustabelle wird an Ort
und Stelle ueberschrieben, `Running` → `Completed`.
**Aufgenommen:** 2026-09-18, Zustand um 04:00:35 UTC (`updated_at`)

Genau diese Ueberschreibung ist der Grund, warum das Gate in einer Schleife
liest statt einmal: ein einmal gelesener Text ist kein Beleg.

## `kontingent.txt`, `environment.txt`

Die beiden Ausfallmeldungen, woertlich aus `CLAUDE.md` Teil 1 uebernommen, wo
sie am 21.–23.8.2026 in `malkreide/*-mcp` aufgezeichnet wurden. Nicht in
diesem Repo beobachtet — deshalb hier als Zitat gekennzeichnet und nicht als
eigene Messung.
