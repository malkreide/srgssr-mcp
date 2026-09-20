# Codex-Messreihe

Die Rohwerte zu «Wenn Codex gar nicht erst hinsieht» in `CLAUDE.md`. Dort
stehen die Lehrsätze, hier die Zahlen — getrennt, weil das Eintragen einer
Zeile dreimal hintereinander Befunde in der Konventionen-Datei erzeugt hat
(#126, #127, #128). Eine Konventionen-Datei ist kein Messprotokoll.

**Diese Datei ist die einzige Stelle, an der diese Zahlen stehen.**
`tests/test_codex_messreihe.py` sichert das zu: Es zählt die Tabellenzeilen
und hält sie gegen jede Zahlwort-Behauptung hier **und** in `CLAUDE.md`, und
es verbietet jeden Einzelwert der Tabelle in der Prosa beider Dateien. Was
dreimal von Hand vergessen wurde, ist damit ein roter Check.

## Ready bis Merge, je Lauf

**Eine Zeile je PR, und zwar der Lauf, den «ready» ausgelöst hat.** Unter #128
liefen drei Durchgänge auf drei Heads: der eingetragene, ein von Hand
angestossener auf `65b9825` (Start 16:47:21,89, `Completed` 16:51:42,55, also
260,7 s intern — der längste gemessene Lauf überhaupt) und ein dritter Versuch
auf `416f83c`, der am erschöpften Kontingent scheiterte. Die Spalten sind auf
den ready-Auslöser definiert; die übrigen Läufe stehen deshalb hier im Text
und nicht in der Tabelle, weil ihre «bis Start»-Werte eine andere Basis
hätten.

| PR | Datum | ready | gemergt | Review startet | Review fertig | bis Start | Laufzeit | intern |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| #103 | 29.8.2026 | 12:41:51 | 12:41:53 | 12:41:58 | 12:43:00 | 7 s | 69 s | 62 s |
| #105 | 29.8.2026 | 16:57:01 | 16:57:04 | 16:57:06 | 16:58:24 | 5,8 s | 83 s | 78 s |
| #113 | 17.9.2026 | 18:50:03 | 18:50:13 | 18:50:10 | 18:51:21 | 7,4 s | 78 s | 70,9 s |
| #114 | 17.9.2026 | 19:06:56 | 19:07:01 | (ungemessen) | 19:07:44 | — | **48,5 s** | — |
| #115 | 18.9.2026 | 03:52:49 | 03:52:57 | (ungemessen) | 03:54:08 | — | 79,0 s | — |
| #116 | 18.9.2026 | 03:59:23 | 03:59:35 | 03:59:29 | 04:00:35 | 6,5 s | 72,1 s | 65,6 s |
| #117 | 18.9.2026 | 05:18:02 | 05:18:07 | 05:18:11 | 05:19:33 | **9 s** | 91 s | 82,2 s |
| #118 | 18.9.2026 | 06:10:06 | **06:13:07** | 06:10:11 | 06:12:20 | 5 s | **rund 135 s** | 129,4 s |
| #125 | 20.9.2026 | 09:00:48 | **09:28:15** | 09:00:55 | 09:02:41 | 7 s | 113 s | 106,3 s |
| #126 | 20.9.2026 | 16:17:07 | 16:22:10 | 16:17:12 | 16:20:31 | 5,5 s | **204 s** | **198,5 s** |
| #127 | 20.9.2026 | 16:28:44 | 16:32:34 | 16:28:51 | 16:31:29 | 7,1 s | 165 s | 158,2 s |
| #128 | 20.9.2026 | 16:39:54 | 17:01:36 | 16:40:04 | 16:42:38 | **10,4 s** | 164 s | 153,4 s |

«bis Start» ist ready → «Review startet», «Laufzeit» ready → «Review fertig»,
«intern» der Startzeitpunkt aus der Statustabelle («Running since …») →
`Completed`. Die ready-Zeitpunkte von #117, #118 und #125 bis #127 sind auf
±1 s genau — abgeleitet aus dem Event-Zeitstempel und der Erzeugung des
Gate-Jobs; alle übrigen Werte stehen sekundengenau in der API.

**Die Tabelle hinkt zwangsläufig um einen Lauf hinterher, und das ist keine
Nachlässigkeit.** Ein PR, der diese Datei ändert, löst beim Umschalten auf
ready selbst einen Codex-Lauf aus — dessen Merge-Zeitpunkt er nicht kennen
kann, weil er zum Schreibzeitpunkt noch offen ist. Die letzte Zeile stammt
deshalb immer vom *vorigen* PR. «Zwölf Läufe» heisst hier «zwölf
aufgezeichnete», nicht «zwölf stattgefundene»; wer die Zahl als Stichprobengrösse
liest, zählt einen zu wenig.

Diese Rekursion ist der Grund, warum jeder PR an dieser Stelle dieselbe Art
Befund produziert: Eine Zeile einzutragen heisst, alles Abgeleitete
nachzuführen — Zähler, Spanne, «sieben der zwölf», die Zwei-Minuten-Regel —, und
wer nur die Zeile einträgt, hat die Drift wieder eingebaut. Beim Eintragen von
#126 ist genau das passiert, an drei Stellen, gefunden vom Review des
Folge-PR, und beim Eintragen von #127 noch einmal an zwei.

Den Handgriff dazu macht `tests/test_codex_messreihe.py`; von Hand gefahren
hat er zweimal versagt. Beim Eintragen von #127 blieb der alte Zähler am
Satzanfang stehen — dort gross geschrieben, und die Suche lief
case-sensitiv. Und das Muster im Test verlangte anfangs einen Artikel vor
dem Zahlwort, weshalb es in **dieser** Datei überhaupt nichts fand und
trotzdem grün meldete.

Zweimal dieselbe Klasse: Eine Prüfung, die eine Schreibweise nicht kennt,
meldet «sauber» und meint «nicht gesucht». Der Test trägt deshalb eine
Positivkontrolle — findet sein Muster gar nichts, fällt er.
