## Was ändert sich

<!-- Kurz: was und warum. -->

## Vor dem Mergen

Der grüne Check `review-abgeschlossen` sagt, dass Codex **gelaufen** ist —
nicht, dass er nichts gefunden hat. Die Befunde stehen in einem
Review-Objekt, nicht in der Statustabelle; wer nur die Kommentare liest,
sieht `Completed` und übersieht sie.

Am 20.9.2026 ist das zweimal hintereinander passiert: #126 und #127 wurden
je ein bis zwei Minuten nach den Befunden gemergt. Beide Male lag die
Korrektur danach auf dem Branch und nirgends sonst, beide Male brauchte es
einen Folge-PR, und beide Male trug `main` zwischenzeitlich einen Text, der
sich selbst widersprach.

- [ ] Review-Objekte abgefragt (`get_reviews`), keines mit offenem Befund
- [ ] Review-Threads abgefragt (`get_review_comments`), keiner offen
- [ ] Codex-Review beantwortet oder behoben — kein offener Befund beim Merge
