# CLAUDE.md

## Teil 1 — Konventionen (portfolio-weit)

### Vor der Arbeit

Klon-Aktualität prüfen — Standard-Branch ermitteln, nicht `main` annehmen:

```bash
B=$(git ls-remote --symref origin HEAD | sed -n 's|^ref: refs/heads/\([^[:space:]]*\).*|\1|p')
git fetch origin "${B:?Standard-Branch nicht ermittelbar}" &&
  git rev-list --count HEAD..FETCH_HEAD
```

Drei Server im Portfolio heissen ihren Standard-Branch `master`
(`openlex-mcp`, `swiss-courts-mcp`, `swisstopo-mcp`); dort scheitert ein fest
verdrahtetes `origin/main` mit «couldn't find remote ref main». Wer das für ein
Netzproblem hält, arbeitet weiter auf genau dem veralteten Klon, vor dem dieser
Absatz warnt. Den `:?`-Schutz nicht weglassen: Bei leerem `B` fetcht git still
den Remote-HEAD und endet mit 0.

Ein veralteter Klon erzeugt eine rote CI, deren Ursache nicht im Diff steht.
Am 3.8.2026 zweimal passiert — beide Male fehlten genau die Commits, die
das Gate einführten, an dem der Branch scheiterte.

Gates lokal fahren, mit der GEPINNTEN ruff-Version aus der CI. Eine andere
Version meldet Abweichungen, die niemand verursacht hat.

### Tests

Gegenprobe ist Pflicht. Ein Test, der grün bleibt, wenn man die
Implementierung entfernt, prüft nichts. Jede neue Zusicherung einzeln
neutralisieren und zeigen, dass genau die zugehörigen Tests fallen.

Zwei Fallen, die beide grün blieben:

- Eine Fake-Uhr, die nur beim Schlafen vorrückt, kann eine Zusicherung über
  echte Zeit nicht widerlegen.
- `monkeypatch.setattr(modul.asyncio, "sleep", ...)` greift ins Modul
  `asyncio` selbst und entschärft die Mechanik im ganzen Prozess. Patche
  einen Modul-Alias (`_sleep = asyncio.sleep`), nicht das fremde Modul.

Handgeschriebene Fixtures kodieren die Annahme des Autors und können sie
nicht widerlegen. Mindestens eine aufgezeichnete Antwort pro externem
Endpunkt, mit Aufnahmedatum.

### Wenn etwas rot ist

Roter Live-Test: erst die Quelle abfragen, dann einordnen. Nicht aus der
Fehlermeldung schliessen. Am 3.8.2026 hiess "nicht gefunden" nicht, dass der
Datensatz weg war, sondern dass die Quelle die Schreibweise ihrer Kopfzeile
gewechselt hatte — vier von sechs Datensätzen produktiv kaputt, alle
Unit-Tests grün.

**Ein 4xx ist kein Nein.** Am 29.8.2026 antwortete `past-publications` in
`swiss-procurement-mcp` auf jede Publikation mit Losen mit HTTP 400. Daraus war
geschlossen worden, die Quelle verweigere diese Auskunft; der Befund stand
datiert im Fixture-Nachweis, ein Test bestätigte ihn, alles blieb grün. Die
Spec desselben Endpunkts führt einen als *optional* deklarierten Parameter
`lotId` — für Publikationen mit Losen ist er Pflicht. Mit ihm antwortet
dieselbe Publikation mit 200. Ein Projekt trug sieben Vorgängerpublikationen,
die der Server als «Quelle nicht erreichbar» wegwarf.

Drei Handgriffe daraus:

- **Die Parameterliste der Spec durchgehen, bevor ein Statuscode eingeordnet
  wird.** «Optional» heisst dort oft «optional für die Mehrheit».
- **Einer deterministischen Absage keinen Wiederholungsrat geben.** «Nicht
  erreichbar, bitte später erneut» ist bei einem 400 falsch und liest sich für
  das Modell wie eine Störung. Den Status mitführen und den fehlenden
  Parameter benennen — den Status, nicht den Antwortkörper.
- **Beide Antworten aufzeichnen, mit und ohne den Parameter.** Eine
  Aufzeichnung nur des Fehlschlags kann nicht zeigen, dass er vermeidbar war;
  dass nur der 400er aufgezeichnet war, ist der Grund, warum der falsche
  Befund nicht auffiel.

**Und ein 403 ist gar keine Auskunft.** Am 29.8.2026 sollten für 42 Repos die
Dependabot-Labels nachgemessen werden. Alle 13 Abfragen des ersten Stapels
kamen zurück als:

```
Failed to find label: API rate limit already exceeded for user ID 8864492.
```

Der gefährliche Teil steht vorn: Das Werkzeug verpackt eine Sperre als
Fund-Fehlschlag. Wer die Zeile überfliegt oder nur auf ein leeres Ergebnis
prüft, zählt 39 Repos als «Label fehlt» und hat seine eigene Erschöpfung
gemessen. Das Limit hängt am Konto, nicht am Repo — derselbe Vormittag hatte
es mit 42 eröffneten und 42 gemergten PRs verbraucht.

Das ist der Absatz darüber, andersherum gelesen: dort war ein 400 eine echte,
wiederholbare Antwort und galt als Störung; hier ist eine Störung als Antwort
verpackt. Entscheidend ist nie der Statuscode, sondern ob die Quelle überhaupt
geantwortet hat.

- **Positivkontrolle im selben Repo.** Ein «nicht gefunden» wird erst dadurch
  zur Messung, dass eine gleichzeitige Abfrage etwas findet.
- **Die Messung entlang der Sperre teilen.** `raw.githubusercontent.com` ist
  ein CDN und nicht die REST-API. Um 11:19:27 UTC lieferte es für
  `register-mcp` HTTP 200, während die Label-Abfrage desselben Repos in
  derselben Minute die Sperre meldete. Alle 42 `dependabot.yml` kamen so
  durch, während die Label-Hälfte stand.
- **Am Token vorbei geht es nicht.** Beide Umwege enden am Agent-Proxy, und
  jeder mit einer eigenen irreführenden Begründung. `api.github.com` ohne
  Zugangsdaten:

  ```
  GitHub access is not enabled for this session. An org admin must connect
  the Claude GitHub App for this organization.
  ```

  Das ist keine Aussage über die Organisation, sondern das, was ohne Token
  kommt. Wer ihr folgt, sucht einen Admin für ein Problem, das keiner hat.
  Die HTML-Seite `github.com/<owner>/<repo>/labels` fällt ebenfalls, aber
  anders:

  ```
  This GitHub API path is not available: sessions are bound to their
  configured repositories. Use repository-scoped endpoints
  (repos/{owner}/{repo}/...).
  ```

  Der Proxy behandelt also auch `github.com` als API-Pfad; die zweite Meldung
  klingt nach einem Scope-Problem und ist doch nur dieselbe Sackgasse. Den
  Token aus der Umgebung in einen curl-Header zu setzen, blockiert der
  Klassifikator. Ob es überhaupt hülfe, ist offen: die Sperre nennt ein
  Nutzerkonto, und ob der Token zu diesem gehört, wurde nie geprüft.
- **Die Sperre gilt nicht dem Dienst, sondern dem Zugangspfad.** Unmittelbar
  nachdem eine Abfrage der Checks eines PR sauber durchlief, meldete die
  Label-Abfrage weiter die Sperre. Von einem blockierten Werkzeug also nicht
  auf «GitHub ist zu» schliessen — und umgekehrt eine gelungene Abfrage nicht
  als Entwarnung für die gesperrte nehmen. Das ist dieselbe Asymmetrie wie
  bei der verschwundenen Codex-Meldung weiter unten.

Wann die Sperre fällt, geben diese Beobachtungen nicht her. Die Meldung nennt
keinen Zeitpunkt, und die `X-RateLimit`-Kopfzeilen sind hinter dem Proxy nicht
zu sehen. Belegt sind drei gesperrte Zeitpunkte — 11:14, 11:16 und 11:19 UTC.
Wer daraus eine Dauer macht, hat sie erfunden.

**Dieselbe Falle bei einer Konfigurationsoption: die Vorgabe lesen, bevor man
einen Schlüssel für wirkungslos hält.** Am 29.8.2026 fielen die
`labels:`-Zeilen aus den `dependabot.yml` des Portfolios, begründet mit
«Dependabot legt Labels nicht an». Eine Messung danach zeigte, dass
`dependencies` in 36 von 42 Repos sehr wohl existiert, 35 davon mit GitHubs
Standardbeschreibung. Das las sich zuerst wie ein Beleg, dass die Aktion
falsch war.

Die Optionsreferenz kehrt es um:

```
Dependabot creates these default labels automatically, as necessary in
your repository.

If you define more than one package manager, an additional label for the
ecosystem or language is added to each pull request.

The labels specified are used instead of the default labels.
```

Ohne `labels:` vergibt Dependabot also `dependencies` — und, sobald mehr als
ein Paketmanager deklariert ist, zusätzlich ein Ökosystem-Label — und legt sie
selbst an; eine eigene Liste **ersetzt** diesen Satz, und «if any of these
labels is not defined in the repository, it is ignored». Die Zeile war nicht
wirkungslos — sie tauschte einen sich selbst pflegenden Vorgabesatz gegen eine
starre Liste.

**Die Bedingung nicht weglassen.** Bei nur einem Paketmanager steht das
Ökosystem-Label gar nicht zu; wer es dort trotzdem erwartet, schreibt genau
den Fehlbefund auf, gegen den dieser Abschnitt geschrieben ist — der Abschnitt
liefe an sich selbst vorbei. Im Portfolio deklariert jede `dependabot.yml`
zwei (`pip` und `github-actions`), die Bedingung ist hier also überall
erfüllt; anderswo nicht unbedingt. Aufgefallen ist die fehlende Bedingung
nicht beim Schreiben, sondern durch einen Codex-Review auf
`swiss-environment-mcp` PR #113 — vierzehn Sekunden vor dem Merge desselben
PR.

Was das kostet, ist an `openlex-mcp` gemessen: zwei Ökosysteme deklariert,
also stünden `dependencies` **und** ein Ökosystem-Label zu; vorhanden ist nur
das erste, `github-actions` und `github_actions` fehlen beide (Kontrolle `bug`
vorhanden). `register-mcp` ist die Gegenprobe: dort existieren alle vier
deklarierten Namen mit handgeschriebener Beschreibung, die Liste ist gewollt
und vollständig.

**Dreimal falsch eingeordnet, in drei Richtungen.** Erst die Zeile für bloss
wirkungslos gehalten. Dann die gefundenen Labels für einen Widerspruch. Dann,
auf denselben Fund gestützt, einen richtigen PR geschlossen mit dem Argument,
das Label existiere ja — obwohl es existiert, *weil* die Vorgabe es anlegt.
Der dritte Fehler ist der teuerste, weil er wie eine Messung aussah.

Was die Messung **nicht** hergibt: wer die 36 Labels angelegt hat. Die
Referenz sagt, Dependabot tue es; die Objekt-IDs liegen aber so dicht
beieinander, dass sie eher aus einem Stapellauf stammen. Beides passt zum
Befund, keines ist belegt — die Herkunft blieb ungemessen.

Beim Aufräumen gilt deshalb dieselbe Frage wie bei `lotId`: Was ist die
*Vorgabe*, wenn man das Ding weglässt — nicht bloss, ob der aktuelle Wert
etwas bewirkt.

**`results[0]` ist nur so verlässlich wie die Zusicherung danach.** Pinnt die
Abfrage einen bekannten Datensatz, ist der erste Treffer eine Drift-Wache und
in Ordnung. Hängt die Zusicherung dagegen davon ab, *welche* Variante die
Quelle heute zuoberst hat, prüft der Test den Tag: am 25.8.2026 rot, weil die
neueste Zürcher Publikation zufällig Lose hatte, am 26.8. grün, ohne dass sich
etwas geändert hätte. Den Fall gezielt wählen und beide Zweige fahren.

PR ohne jeden Check ist selten ein Repo ohne CI, meistens ein
Merge-Konflikt: GitHub berechnet dafür keinen Merge-Commit und startet nichts.

Ein Codex-Review auf einem PR wird beantwortet oder behoben, nie ignoriert.

### Wenn Codex gar nicht erst hinsieht

Die Zeile oben unterstellt, dass es einen Befund geben *kann*. Das ist nicht
immer so, und man sieht es dem PR nicht an.

Am 21.8.2026 war das Code-Review-Kontingent zwischen 08:41 und 09:48
aufgebraucht — davor echte Reviews, danach in 30 Repos nur noch:

```
You have reached your Codex usage limits for code reviews.
```

**Der Text ist seither länger geworden.** Am 18.9.2026 um 06:40:13 UTC kam die
Meldung zum ersten Mal in diesem Repo, unter PR #119, und lautete wörtlich:

```
You have reached your Codex usage limits for code reviews. You can see your limits in the [Codex usage dashboard](https://chatgpt.com/codex/cloud/settings/usage).
```

Zwei Dinge daran sind praktisch:

- **Das Suchmuster des Gates hat gehalten**, weil es nur
  `reached your Codex usage limits` verlangt. Ein Muster, das den ganzen Satz
  gefordert hätte, wäre an dieser Drift gescheitert — und zwar still, weil ein
  nicht gefundener Ausfalltext nicht rot wird, sondern das Fenster auslaufen
  lässt und dann rot wird, mit der falschen Begründung «kein Review».
- **Die Aufzeichnung ist jetzt echt.** `kontingent.json` trug bis dahin ein
  Zitat mit gesetzten IDs und Zeitstempeln, im Nachweis ausdrücklich als
  schwächste der Aufzeichnungen benannt. Genau diese Schwäche hat sich
  bestätigt: Das Zitat war die kürzere, ältere Form.

Wie lange die Sperre dauerte, geben die Beobachtungen nur als Spanne her. Vier
Zeitpunkte sind belegt: letzter gelungener Review am 21.8. um 08:41, erste
Limit-Meldung um 09:48, letzte beobachtete Limit-Meldung am 22.8. um 11:03,
erste *andere* Meldung am 23.8. um 08:22.

Zwischen erster und letzter Limit-Meldung liegen **25 h 15 min**. Das ist der
Abstand zweier Fehlschläge, nicht die Dauer einer Sperre. Wer ihn Untergrenze
nennt, hat die durchgehende Erschöpfung schon vorausgesetzt, die er belegen
soll: Öffnete sich das Fenster zwischendurch und schloss es sich durch neue
Auslöser wieder, waren es zwei kurze Sperren und nie eine von 25 Stunden.
Untergrenze einer *einzelnen* Sperre sind die 25 h 15 min nur unter genau dieser
Annahme — und die ist unbelegt.

Nach oben trägt die Rechnung dagegen. Die längste mit den Beobachtungen
verträgliche Sperre reicht vom letzten Erfolg um 08:41 bis zur abweichenden
Meldung um 08:22, also **47 h 41 min**; länger kann keine einzelne gewesen sein.
Wer stattdessen ab der ersten Limit-Meldung rechnet, unterschlägt die 67
Minuten, in denen das Kontingent schon weg gewesen sein kann, und nennt die
Spanne zwischen zwei Beobachtungen eine Obergrenze.

Beobachtungspunkte sind keine Messreihe — die 21 Stunden vor der abweichenden
Meldung liefen ganz ohne Codex-Auslöser, dort hat niemand gemessen.

In der Zwischenzeit sind 32 PRs mit formal erfülltem Häkchen gemergt worden,
ohne dass jemand hineingesehen hat, und am 22.8. noch einmal 43.

**Vier** Gründe, warum Codex schweigt, und nur einer davon ist harmlos:

- **Kein Befund** — dann schreibt er einen gewöhnlichen Issue-Kommentar:

  ```
  Codex Review: Didn't find any major issues. Swish!
  ```

  Der Schlusssatz wechselt bei jedem Lauf («Delightful!», «Keep it up!»,
  «More of your lovely PRs please.»); stabil ist nur der Satz davor. Der
  Infokasten, den Codex unter jeden Review setzt, behauptet weiterhin eine
  Reaktion («otherwise it will react with 👍») — am 23.8. kam in sechs Repos
  die Meldung und in keinem die Reaktion. Der Kasten ist keine Quelle.
- **Der PR ist ein Draft** — dann läuft kein Review an. Dass deshalb *gar
  nichts* kommt, stimmt seit dem 18.9.2026 nicht mehr; siehe den Nachtrag
  «Die Environment-Meldung ist kein Befund» weiter unten.
- **Das Kontingent ist weg** — dann schreibt er die Meldung oben.
- **Für das Repo fehlt eine Environment** — dann schreibt er:

  ```
  To use Codex here, create an environment for this repo.
  ```

Der vierte kam erst zum Vorschein, als der dritte wegfiel, und das ist kein
Zufall: Die Prüfungen liegen hintereinander. Dass es diese Reihenfolge ist und
nicht die umgekehrte, lässt sich an einem einzigen Repo ablesen — in
`swiss-public-data-mcp` bekam PR #54 am 22.8. um 10:56:55 die Kontingent-Meldung
und PR #56 am 23.8. um 08:22:20 die Environment-Meldung. Läge die
Environment-Prüfung vorn, hätte #54 sie schon am Vortag gesehen; die Environment
fehlte ja bereits. Zwei Meldungen aus demselben Repo schlagen hier jede
Vermutung über die Reihenfolge.

**Die Environment-Meldung ist kein Befund.** Am 18.9.2026 um 04:12:00 UTC kam
sie in diesem Repo unter PR #117, elf Sekunden nach dem Eröffnen — als Draft.
Wörtlich, und anders als oben zitiert mit Link:

```
To use Codex here, [create an environment for this repo](https://chatgpt.com/codex/cloud/settings/environments).
```

Die Environment fehlt dabei nachweislich **nicht**: elf Minuten zuvor, um
04:00:35, hatte PR #116 im selben Repo einen vollständigen Review bekommen, und
Codex' eigener Infokasten dort sagt «Your team has set up Codex to review pull
requests in this repo».

Zwei Sätze oben fallen damit:

- «Darauf läuft Codex nicht an» — auf einem Draft kommt sehr wohl ein
  Kommentar, nur kein Review. Der kommentarlose Draft war nie der einzige Fall.
- «Für das Repo fehlt eine Environment — dann schreibt er» — die Umkehrung
  gilt nicht. Der Text kommt auch, wenn sie da ist.

Was der Text **bedeutet**, ist damit offen, und das bleibt hier so stehen. Die
naheliegende Lesart — Codex antwortet auf den Draft-Auslöser mit einer generischen
Meldung, weil er keinen Review starten kann — ist ungemessen. Die Beobachtung vom
23.8. in `swiss-public-data-mcp` liesse sich rückwirkend genauso lesen, und ob
jener PR ein Draft war, hat niemand festgehalten. Das ist kein Beleg, sondern eine
zweite Stelle, an der etwas fehlt.

Die Folge wiegt schwerer als die Deutungsfrage: **die Meldung bleibt
stehen.** Ein Kommentar verschwindet nicht, wenn der PR auf ready geht. Wer auf
ihren blossen Text prüft, prüft ab dann für immer positiv — genau das hätte das
Gate in `codex-gate.yml` an diesem PR getan, bevor es am 18.9. umgebaut wurde.

Praktisch heisst das: **Eine verschwundene Limit-Meldung ist keine Entwarnung.**
Sie kann bedeuten, dass das Kontingent wieder da ist — und dass jetzt etwas
anderes den Review verhindert. Belegt ist eine Prüfung erst durch ein
Review-Objekt **oder** eine Befundlos-Meldung. Wer nur das Objekt gelten lässt,
zählt jeden befundlosen Review als ungeprüft — und baut sich denselben Fehlalarm
ein, den dieser Abschnitt verhindern soll, nur in die andere Richtung.

«Kein Kommentar» heisst also nicht «geprüft und sauber». Unterscheiden lässt es
sich an der Form: Ein Review **mit** Befund ist ein Review-Objekt
(«💡 Codex Review», mit Commit-Angabe); ein Review **ohne** Befund und die
beiden Ausfallmeldungen — Kontingent wie Environment — sind gewöhnliche
Issue-Kommentare und trennen sich nur im Text. Beim Draft läuft kein Review an;
ein kommentarloser Draft ist deshalb kein Beleg, sondern ein nicht durchgeführter
Test — und ein *kommentierter* Draft ist es genauso wenig, siehe «Die
Environment-Meldung ist kein Befund» oben.

Das sind verschiedene Abfragen — `get_reviews` fürs Objekt, `get_comments` für
alles andere; wer nur eine nimmt, übersieht den Rest. Genau so ist die
Limit-Meldung zuerst durchgerutscht.

Der Kommentarzähler allein reicht ohnehin nicht: `comments: 1` kann die
Befundlos-, die Kontingent- **oder** die Environment-Meldung sein — drei
gegensätzliche Bedeutungen unter derselben Zahl. Den Text lesen, nicht die Zahl.
Und einen unbekannten vierten Text wörtlich zitieren, statt ihn in eine der
bekannten Schubladen zu zwingen: Dieser Abschnitt musste schon einmal von drei
auf vier Gründe wachsen, und die 👍-Reaktion stand hier zwei Fassungen lang als
Tatsache.

**Seit dem 29.8.2026 gibt es eine weitere Form, und sie ist keine der bekannten.**
In `srgssr-mcp` meldete sich Codex unter PR #103 nicht mit einem der bekannten
Texte, sondern mit einer Statustabelle:

```
## Codex Review Summary

| Review | Status | Commit | Review trigger |
| 📝 **Code Review** | ✅ **Completed** 2026-08-29T12:43:00Z | `ca747ea` | Draft marked ready |
```

Zweierlei daran ändert das Vorgehen oben.

**Der Kommentar wird überschrieben, nicht ergänzt.** Dieselbe ID (5462475643)
trug um 12:42:01 noch `🔄 Running` und um 12:43:03 `✅ Completed`. Ein Text, der
einmal gelesen wurde, ist damit kein Beleg mehr — `created_at` und `updated_at`
gehen auseinander, und wer zu früh liest, hält einen laufenden Review für das
Ergebnis. Aus den drei Bedeutungen unter `comments: 1` werden damit fünf — und
zwei davon liegen nacheinander in derselben Zahl, an derselben ID.

**Die Befundlos-Meldung blieb aus.** Kein «Didn't find any major issues», kein
Review-Objekt (`get_reviews` gab `[]`), nur die Tabelle auf `Completed`. Wer
nach dem alten Satz sucht, zählt diesen Lauf als ungeprüft — genau der
Fehlalarm, den der Absatz oben in die andere Richtung verhindern soll. Die neue
Form ist als Beleg dabei *stärker* als der alte Satz: sie nennt Commit und
Auslöser, er nannte keines von beidem.

Die zweite Beobachtung kam vier Stunden später, unter PR #105 im selben Repo:
wieder die Tabelle, neue Kommentar-ID (5463680232), Commit `1bd0a23`, Auslöser
«Draft marked ready», wieder `Running` → `Completed` an Ort und Stelle, wieder
`get_reviews` → `[]` und keine Befundlos-Meldung. Die Form ist damit **kein
Einzelfall** — was der Absatz vorher offenliess.

Die dritte kam am 17.9.2026 unter PR #113, wieder `srgssr-mcp`: Kommentar-ID
5719569936, Commit `005c66c`, Auslöser «Draft marked ready», `Running` →
`Completed` an derselben ID, `get_reviews` → `[]`, keine Befundlos-Meldung.
Das ist **dieselbe Form 19 Tage später** und damit das, was den beiden Läufen
vom 29.8. fehlte: ein zweites Datum. Der Einwand stand hier bis zu diesem
Nachtrag als «zwei Läufe an einem Repo an einem Tag sind keine Messreihe» —
seine erste Hälfte ist beantwortet, die zweite nicht: das Datum ist nicht mehr
eines, das Repo schon.

Die vierte kam am selben Abend unter PR #114, 17 Minuten nach der dritten:
Kommentar-ID 5719773021, Commit `215a223`, wieder `Running` → `Completed` an
derselben ID, `get_reviews` → `[]`, keine Befundlos-Meldung. Drei weitere am
18.9.2026, alle mit demselben Ablauf und demselben leeren `get_reviews`:
PR #115 (ID 5724899490, Commit `4a270e3`), PR #116 (ID 5724943260, `0ee99ed`)
und PR #117 (ID 5725538956, `f69be45`).

**Der achte Lauf brach die Serie**, und zwar an der Stelle, die der Abschnitt
oben vorhersagt: Unter PR #118 (ID 5725947917, `93bc690`) lief dieselbe Tabelle
`Running` → `Completed`, aber `get_reviews` gab diesmal **kein** `[]`, sondern
ein Review-Objekt (5244784664) mit einem P2-Befund. Die Unterscheidung «Befund
→ Review-Objekt, kein Befund → Issue-Kommentar» hält also auch neben der
Statustabelle; die Tabelle ersetzt das Objekt nicht, sie steht daneben. Wer
nur `get_comments` liest, sieht `Completed` und übersieht den Befund.

**Diese Aufzählung hinkte zwei Läufe hinterher.** Der Lauf unter #116 stand
nur in der Laufzeit-Liste unten, nicht hier — gezählt wurde, was gerade
gebraucht wurde. Eine Zählung, die an zwei Stellen geführt wird, driftet; das
ist dieselbe Mechanik wie beim ruff-Literal, nur ohne roten Check, der es
meldet.

Was die acht Läufe nicht hergeben: dass die Tabelle den alten Text *überall*
ersetzt. Alle acht stehen in **einem** Repo. Über zwei Tage und acht Läufe
hinweg ist die Form dort stabil, über das Portfolio sagt sie nichts, und ob der
alte Satz anderswo noch kommt, hat niemand nachgesehen. Bis dahin gilt beides
als möglicher Beleg — und ein weiterer unbekannter Text wird wörtlich zitiert,
nicht einsortiert.

Die Laufzeit **streut weiter, als hier zwei Fassungen lang stand.** Von ready
bis `Completed` — die Basis, die für alle acht Läufe öffentlich ablesbar ist:
69 s unter #103, 83 s unter #105, 78 s unter #113, **48,5 s unter #114**,
79,0 s unter #115, 72,1 s unter #116, 91 s unter #117 und **rund 135 s unter
#118**. Der Satz davor lautete «das Fenster von gut einer Minute bis
knapp achtzig Sekunden hält also», geschrieben in #114 auf drei Beobachtungen —
und derselbe PR hat ihn beim Mergen widerlegt, neunzehn Minuten später. Drei
Punkte, die nebeneinanderliegen, sind keine Untergrenze; sie sind drei Punkte.

Die interne Laufzeit («Running since …» bis `Completed`) ist nur für drei
davon bekannt: 62 s unter #103 (12:41:58,07 → 12:43:00,23), 78 s unter #105
(16:57:06,81 → 16:58:24,64), 70,9 s unter #113 (18:50:10,42 → 18:51:21,28),
65,6 s unter #116 (03:59:29,51 → 04:00:35,09), 82,2 s unter #117
(05:18:11,20 → 05:19:33,44) und **129,4 s unter #118**
(06:10:11,34 → 06:12:20,77). Für #114 und #115 fehlt sie, weil erst nach `Completed` gelesen wurde und die
Tabelle den Startzeitpunkt dann nicht mehr zeigt. Aus dem `created_at` des
Kommentars gerechnet wären es 41,5 s bzw. 65,0 s, aber das ist eine andere
Basis — der Kommentar entsteht zwei bis drei Sekunden nach dem Start. **Die
beiden Basen nicht mischen**; wer 41,5 gegen 62 stellt, vergleicht zwei
Messgrössen.

**Und der Absatz selbst ist darauf hereingefallen.** Der Abstand zwischen Merge
und Gate-Ergebnis stand hier zuerst mit 86 Sekunden — das ist der Abstand zum
*Codex*-`Completed` um 05:19:33, nicht zum Gate-Ergebnis um 05:19:39; richtig
sind 92 Sekunden. Zwei Endpunkte, sechs Sekunden auseinander, und die falsche
Zahl untertreibt genau das, worum es in dem Satz geht. Gefunden hat es der
Codex-Review auf #118, also die Instanz, die das Gate schützen soll. Eine Regel
zu kennen, schützt nicht davor, sie zu brechen — ein zweiter Leser schon.

Praktisch heisst das: **48,5 s bis rund 135 s**, nach acht Läufen. Das ist die
vierte Fassung dieses Satzes, und die dritte wurde kassiert, **während der PR
offen war, der sie schrieb**: #118 trug «48,5 s bis 91 s» ein, und der
Codex-Lauf auf ebendiesem PR brauchte 129,4 s.

Damit ist keine Fassung dieses Satzes je einen Tag alt geworden. Eine gemerkte
Zahl ist hier nicht bloss ungenau, sie ist das falsche Werkzeug — den
Startzeitpunkt aus der Tabelle lesen, nicht das Fenster erinnern.

**Deshalb die Startzeit lesen, nicht das Fenster erinnern.** Der Absatz oben
warnt davor, zu früh zu lesen und einen laufenden Review für das Ergebnis zu
nehmen. Unter #113 lag der Fehler andersherum nahe: die Tabelle stand auf
`Running`, der PR war schon gemergt, und «der Lauf hängt, weil der PR unter
ihm zuging» klang plausibel. Es waren 56 Sekunden seit dem Start. Die Tabelle
nennt ihn selbst («Running since …»); die Differenz zur aktuellen Zeit kostet
eine Zeile. Das ist der Handgriff, der die Korrektur oben überlebt hat — die
Zahl daneben nicht. Ohne ihn ist `Running` nur ein Wort.

Die 👍-Reaktion hat der Infokasten übrigens neu formuliert («reacts with 👀
while any review is running … and reacts with 👍 once all reviews finish with no
findings») und weiterhin nicht geliefert: `reactions.total_count` war `0`, weder
während des Laufs noch danach — zuletzt unter #118, also in allen acht
Beobachtungen. Unter #118 fällt dabei genau die 👀-Hälfte der Behauptung: Der
Lauf hatte einen Befund, das 👍 stand also ohnehin nicht zu, aber während der
129 Sekunden Laufzeit war auch kein 👀 da. Der Kasten bleibt keine Quelle.

**Und diese drei Zählungen hingen wieder hinterher** — «sieben», nachdem der
achte Lauf zwei Absätze höher eingetragen war. Der Absatz über die driftende
Zählung hat also beim Schreiben seiner eigenen Fortsetzung wieder gedriftet.
Das ist kein Argument gegen das Zählen, sondern dafür, es an einer Stelle zu
tun; solange es an dreien steht, ist die nächste Drift eingebaut.

Und ein befundloser Lauf ist kein Freispruch. Am 23.8. lief derselbe Text durch
42 Reviews: 36 meldeten denselben P2-Befund, 6 die Befundlos-Meldung — gleiche
Eingabe, gegenteiliges Urteil, alles in denselben neun Minuten. Ein sauberer
Lauf sagt damit etwas über den Lauf, nicht über den Text. Wer sein Häkchen
daran hängt, hängt es an einen Münzwurf.

Portfolio-weit nachsehen:

```
search_pull_requests: user:malkreide commenter:chatgpt-codex-connector[bot] updated:>=<Datum>
```

Findet nur, wo er *kommentiert* hat. Repos ohne PR-Aktivität tauchen nicht auf
— das ist kein Beleg, dass dort geprüft wurde.

Zweiter Weg, den Prüfer zu verlieren, ganz ohne Kontingentproblem: zu schnell
mergen. Am 21./22.8. lagen zwischen «ready for review» und Merge mehrfach drei
bis fünf Sekunden. Codex wird beim Umschalten von Draft auf ready ausgelöst und
braucht danach Zeit; wer sofort mergt, hat das Häkchen gesetzt und den Review
nicht abgewartet.

Wie viel Zeit, ist inzwischen achtmal durchgemessen, alle acht Male in
`srgssr-mcp`:

| PR | Datum | ready | gemergt | Review startet | Review fertig |
| --- | --- | --- | --- | --- | --- |
| #103 | 29.8.2026 | 12:41:51 | 12:41:53 | 12:41:58 | 12:43:00 |
| #105 | 29.8.2026 | 16:57:01 | 16:57:04 | 16:57:06 | 16:58:24 |
| #113 | 17.9.2026 | 18:50:03 | 18:50:13 | 18:50:10 | 18:51:21 |
| #114 | 17.9.2026 | 19:06:56 | 19:07:01 | (ungemessen) | 19:07:44 |
| #115 | 18.9.2026 | 03:52:49 | 03:52:57 | (ungemessen) | 03:54:08 |
| #116 | 18.9.2026 | 03:59:23 | 03:59:35 | 03:59:29 | 04:00:35 |
| #117 | 18.9.2026 | 05:18:02 | 05:18:07 | 05:18:11 | 05:19:33 |
| #118 | 18.9.2026 | 06:10:06 | **06:13:07** | 06:10:11 | 06:12:20 |

Die ready-Zeitpunkte von #117 und #118 sind auf ±1 s genau — abgeleitet aus dem
Event-Zeitstempel und der Erzeugung des Gate-Jobs; alle übrigen Werte stehen
sekundengenau in der API.

Zwei, drei, zehn, fünf, acht, zwölf und fünf Sekunden bis zum Merge — und dann
**181 Sekunden unter #118**. Sieben der acht Reviews liefen damit vollständig
auf einem bereits geschlossenen PR: unter #113 war das Ergebnis 68 Sekunden
nach dem Merge da, unter #114 entstand die Statustabelle überhaupt erst zwei
Sekunden **nach** dem Merge, und unter #117 begann der Review vier Sekunden
danach. Dass keiner von ihnen etwas fand, ist Glück und nicht Verfahren: ein
Befund wäre an einem gemergten PR gelandet, wo ihn die Regel «beantworten oder
beheben» nur noch über einen Folge-PR erreicht.

**#118 ist die Ausnahme, und sie ist die interessanteste Zeile der Tabelle.**
Dort wurde drei Minuten gewartet, der Review war 47 Sekunden vor dem Merge
fertig — und der PR wurde trotzdem mit einem offenen P2 gemergt. Die Zeile
zeigt damit, dass das Zeitproblem und das Befundproblem zwei verschiedene sind:
Wer lange genug wartet, hat das Ergebnis, aber noch nicht gelesen. Das Glück
von oben war unter #118 aufgebraucht.

**«Fünf bis sieben Sekunden bis zum Start» ist widerlegt, und zwar durch den
PR, der den Einwand dagegen abgeschwächt hatte.** Gemessen sind sechs
Startwerte: 7 s (#103), 5,8 s (#105), 7,4 s (#113), 6,5 s (#116), **9 s
(#117)** und 5 s (#118).

Der Weg dorthin ist die eigentliche Lehre. Für #114 und #115 fehlt der
Startzeitpunkt; ablesbar war nur die Entstehung des Kommentars — 7 s nach ready
unter #114, aber **14 s** unter #115. Daraus stand hier die Vermutung, der Start
könne jenseits von sieben Sekunden liegen. #116 lieferte 6,5 s, also einen Wert
mitten in den drei bekannten, und der Absatz vermerkte, das stütze die Vermutung
**nicht**. Das war richtig und wurde trotzdem als Entwarnung gelesen. #117
liefert 9 s und belegt sie.

Ein Wert, der eine Vermutung nicht stützt, widerlegt sie nicht — auch wenn er
sich so liest. Derselbe Kurzschluss steckte in «rund 40 bis 85 Sekunden» und
ist dort eine Fassung weiter oben ebenfalls korrigiert worden, durch denselben
Lauf.

**Der Abstand wächst nicht monoton, und sieben der acht haben nicht gereicht.**
Zwei, drei, zehn, fünf, acht, zwölf, fünf — gegenüber 48,5 bis rund 135 Sekunden
Laufzeit ist jeder davon bedeutungslos. Wer hier «etwas warten» liest, hat die
Grössenordnung verfehlt.

Der achte hat gereicht und half trotzdem nicht: 181 Sekunden, Ergebnis lag vor,
Befund offen. Eine ausreichende Wartezeit ist eine notwendige Bedingung, keine
hinreichende.

**Die Zwei-Minuten-Regel deckt den langsamsten Lauf nicht mehr.** Sie stand
hier, seit das Maximum bei 83 s lag; unter #118 waren es rund 135 s. Eine feste
Wartezeit muss den langsamsten Lauf decken, nicht den schnellsten — und welcher
das ist, weiss man erst hinterher. Die Zahl ist in dieser Datei viermal nach
oben korrigiert worden, jedes Mal vom nächsten Lauf.

Die Konsequenz ist deshalb keine grössere Zahl, sondern eine andere Methode:
**nicht warten, sondern nachsehen.** Die Statustabelle nennt Commit und Status;
`Completed` für den aktuellen Head ist eine Auskunft, eine abgelaufene Stoppuhr
ist keine. Wer doch eine Zahl braucht, nimmt sie als Untergrenze und prüft
danach trotzdem.

**Ein ausgebliebenes Event ist keine Zustandsauskunft.** Unter #114 wurde
genau daraus ein Fehlbefund: «bisher kein Merge erfolgt», geschlossen aus dem
Umstand, dass noch kein Merge-Event angekommen war. Der PR war zu diesem
Zeitpunkt seit neun Sekunden gemergt; das Event lag in der Warteschlange und
kam eine Runde später. Der Event-Hinweis sagt es selbst («This notice may
arrive out of order; if the PR's state gates your next action, verify it with
a fresh fetch first»), und er sagt es, weil der Kanal nicht dafür gebaut ist,
Abwesenheit zu bedeuten. Wer eine Aussage über den Zustand macht, fragt den
Zustand ab — eine Abfrage kostet einen Aufruf, der Fehlbefund kostet eine
Korrektur.

**Ein vier Minuten alter Zustand ist genauso wenig eine Auskunft.** Unter #118
wurde um 06:12 der Zustand gelesen, um 06:13:07 gemergt, und um 06:16:20 ein
Kommentar «der Head ist jetzt `f8d5980`» an den PR geschrieben — an einen seit
drei Minuten geschlossenen PR, dessen Head `93bc690` geblieben war. Der Push
davor landete auf dem Branch und nirgends sonst: was nach dem Merge gepusht
wird, ist nicht im PR und nicht in `main`, sondern braucht einen neuen PR.
Nicht das Event fehlte diesmal, sondern die zweite Abfrage vor dem Schreiben. Das ist dieselbe Asymmetrie wie bei «Ein 403 ist gar keine
Auskunft» in Teil 1: nichts gehört zu haben heisst nicht, dass nichts
geschehen ist.

Der lehrreiche Teil ist die Wiederholung, und sie hat jetzt sechs Glieder.
#105 war der PR, der diese Falle dokumentiert, und ist ihr zum Opfer
gefallen. #113 führte die Drahtform-Messung ein und fiel ihr mit der Tabelle
bereits im Repo erneut zum Opfer. #114 schrieb die Zwei-Minuten-Regel und
diese Tabelle — und wurde fünf Sekunden nach «ready» gemergt. #115 schrieb den
Satz, dass eine Regel im Text hier nicht greift, und wurde acht Sekunden nach
«ready» gemergt. #116 trug die Zeile über #115 nach und sagte voraus, eine
sechste Zeile wäre «kein neuer Befund mehr, sondern die Bestätigung, dass
keines von beidem eingerichtet wurde» — und wurde zwölf Sekunden nach «ready»
gemergt. Die Vorhersage bewies sich keine dreissig Sekunden später an ihrem
eigenen PR. #117 baute schliesslich das Gate, das den Merge halten soll — und
wurde fünf Sekunden nach «ready» gemergt, eine Sekunde nachdem sein eigener
Gate-Job angelaufen war.

Sechs PRs, zwei Sessions, derselbe Absatz jeweils unmittelbar vor Augen. Die
Regel wird beim Schreiben gelesen und beim Mergen gebraucht, und das sind zwei
verschiedene Handgriffe.

**Das sechste Glied ist von anderer Art, und darin liegt der Ertrag.** Bei den
fünf davor fehlte der Mechanismus. Unter #117 gab es ihn: der Job lief, wartete
92 Sekunden, fand die Statustabelle für den richtigen Head und schloss mit
`success` — 92 Sekunden nach dem Merge. Gescheitert ist nicht die Mechanik,
sondern der eine Handgriff, der in keiner Datei steht. Ein Werkzeug zu bauen
und es nicht scharf zu stellen, sieht von innen aus wie Fortschritt und wirkt
von aussen wie nichts.

**Die beiden Wege, die hier als Abhilfe standen, sind gemessen unbrauchbar —
und einer davon macht es schlimmer.** Beides am 18.9.2026 nachgeprüft:

- «Ein Required Check, den Codex setzt» — **den gibt es nicht.** Über #113,
  #114, #115 und #116 trug jeder PR exakt dieselben sieben Check-Runs
  (`quality` ×3, `test` ×3, `Gitleaks`), alle aus den Workflows dieses Repos.
  Codex meldet sich ausschliesslich als Issue-Kommentar; es gibt nichts zu
  fordern.
- «Auto-Merge statt Sofort-Merge» — **das mergt früher.** Auto-Merge wartet auf
  Required Checks, nicht auf Kommentare. Unter #116 war der letzte Repo-Check
  um 03:59:10 grün, dreizehn Sekunden **vor** dem Ready-Klick und fünfundachtzig
  Sekunden vor dem Codex-Ergebnis. Auto-Merge hätte im Moment des Klicks
  gemergt, also schneller als die zwölf Sekunden, die tatsächlich vergingen.

Das ist derselbe Fehler wie beim Laufzeit-Fenster und beim ruff-Pin, nur an
einer dritten Stelle: eine Abhilfe aufschreiben, ohne sie zu messen. Sie stand
hier zwei Fassungen lang und klang plausibel.

Was bleibt, ist der Umweg über einen Check, den **das Repo selbst** setzt:
`.github/workflows/codex-gate.yml` wartet auf die Statustabelle und schliesst
erst ab, wenn sie für **diesen Head** auf `Completed` steht. Der Workflow
nennt seine Wartezeit und seine Ausnahmen selbst; hier steht keine Kopie
davon. Drei Dinge, die er ausdrücklich nicht kann:

- **Ohne Branch Protection sperrt er nichts**, und das ist seit dem 18.9.2026
  nicht mehr Vorhersage, sondern gemessen. Auf #117 — dem PR, der ihn einführt —
  lief der Job unter dem Namen `review-abgeschlossen` von 05:18:06 bis 05:19:39
  und schloss mit `success`; gemergt wurde um 05:18:07, also 92 Sekunden vor
  seinem Ergebnis und eine Sekunde nach seinem Start. Als Required Check
  eingetragen hält er den Merge-Button; ohne diesen Eintrag ist er ein
  sichtbarer Hinweis — und ein sichtbarer Hinweis ist genau das, was hier
  siebenmal nicht gereicht hat. Der Eintrag ist eine Repo-Einstellung, steht in
  keiner Datei und ist beim Lesen des Workflows nicht zu sehen.
- **Nach Ablauf der Wartezeit lässt er bei einem Ausfalltext durch.** Erschöpftes
  Kontingent oder Environment-Meldung heissen, dass von Codex nichts zu erwarten
  ist; darauf zu blockieren hielte das Repo wegen einer Störung an. Der Lauf sagt
  dann ausdrücklich, dass der PR ungeprüft ist. Ein Gate, das im Normalbetrieb
  anspringt, wird abgeschaltet — die Lehre aus dem ruff-Literal in #114 gilt
  hier genauso.

  Der erste echte Lauf hat diese Ausnahme nebenbei geprüft: Die Draft-Meldung
  stand unter #117 im Thread, und der Job hat trotzdem gewartet statt sie als
  Freibrief zu nehmen. Codex reviewte denselben PR vollständig — womit die
  Meldung ein zweites Mal als Auskunft über eine fehlende Environment
  ausscheidet.

  **Die Reihenfolge ist die Zusicherung.** In der ersten Fassung wurden die
  Ausfalltexte zu Beginn jeder Runde geprüft und beendeten den Job sofort. Mit
  der Draft-Meldung von #117 im Thread hätte das Gate an genau dem PR, der es
  einführt, auf der Stelle durchgelassen — ohne dem Review die Gelegenheit zu
  geben. Jetzt wird zuerst gewartet; die Ausfalltexte entscheiden erst über ein
  *ergebnislos* abgelaufenes Fenster, und was sie bedeuten, muss dafür niemand
  wissen.

  **Und nur der Bot zählt.** Die erste Fassung las jeden Kommentar. Ein Mensch,
  der einen der Ausfalltexte zitiert — etwa in einem PR, der über sie schreibt —,
  entwaffnete das Gate damit.
- **Er prüft den Abschluss, nicht den Befund.** `Completed` heisst «der Review
  ist gelaufen», nicht «er hat nichts gefunden» — und genau so ist es am
  18.9.2026 eingetreten. Unter #118 meldete Codex um 06:12:18 einen P2, das
  Gate schloss um 06:12:26 mit `success`, weil die Tabelle auf `Completed`
  stand, und gemergt wurde um 06:13:07: **49 Sekunden nach dem Befund, mit
  offenem Thread.** Die Korrektur lag da noch nicht einmal geschrieben vor.

  Ein grünes Gate ist also kein sauberer Code, sondern nur ein durchgeführter
  Review. Die Checkliste im PR-Template bleibt die Stelle, an der jemand
  hinsehen muss — das Gate nimmt ihr nichts ab.

  Technisch liesse sich das schliessen: offene Review-Threads sind über die
  API abfragbar. Ob man es *will*, ist eine andere Frage — dann hielte ein
  einzelner Nit-Thread den Merge auf, und ein Gate, das im Normalbetrieb
  anspringt, wird abgeschaltet. Bis das entschieden ist, steht die Lücke hier
  benannt statt unausgesprochen.

Das Kontingent hängt am Konto, nicht am Repo, und Code-Reviews haben einen
eigenen Topf — nur GitHub-getriggerte Reviews zählen hinein. ChatGPT-Pläne
fahren ein rollendes Fünf-Stunden-Fenster plus Wochenlimits; welches greift,
steht im Codex-Dashboard. Welches hier griff, ist **offen**. Die Lücke oben
schliesst das Fünf-Stunden-Fenster nicht aus: Es kann sich zwischendurch
geöffnet und durch neue Auslöser wieder erschöpft haben. Das auszuschliessen
bräuchte den Nachweis, dass in der ganzen Spanne kein einziger Review durchlief
— den gibt es nicht, weil nur Fehlschläge beobachtet wurden. Eine lange Reihe
von Fehlschlägen belegt eine lange Reihe von Fehlschlägen, nicht ihre Ursache.

Zeigt das Dashboard freies Kontingent, während Reviews weiter scheitern, ist
das ein bekannter Fehler bei mehreren verbundenen Konten — dann den
GitHub-Connector in den Codex-Einstellungen trennen und neu verbinden.

Die Environment legt man unter `chatgpt.com/codex/cloud/settings/environments`
an, und zwar **je Repo**. Die Meldung sagt es selbst («for this repo»), und am
23.8. war es genau so: In `swiss-public-data-mcp` fehlte sie, dort kam kein
Review; in den übrigen Repos lief Codex am selben Morgen durch. Eine
Environment fürs Konto genügt also nicht — wer eine anlegt und den Rest für
erledigt hält, mergt weiter Ungeprüftes.

### Wenn zwei Agenten dasselbe tun

Vor dem Anlegen eines Branches mit vorgegebenem Namen prüfen, ob es ihn schon
gibt:

```bash
git ls-remote --heads origin claude/<name> | wc -l
```

Steht dort `1`, arbeitet jemand anderes daran — mit Schreibrecht auf denselben
Ref.

Ein PR mit leerem Diff wird geschlossen, nicht gemergt. Der Test ist
`get_files` auf dem PR: kommt `[]` zurück, ändert er nichts. Ein grüner Check
sagt dazu nichts — die CI prüft den Head, nicht die Differenz zur Basis.

Am 21.8.2026 liefen zwei Sessions dieselbe Aufgabe über 45 Repos, auf den
Branches `claude/codex-review-audit-templates-9sn6mx` und
`claude/codex-review-audit-7ioh56`. Wo die eine zuerst nach `main` kam, wurde
`main` in den Branch der anderen gemergt und der add/add-Konflikt zugunsten
von `main` aufgelöst. Übrig blieben 14 PRs, die durch sämtliche Gates grün
liefen und nichts enthielten; sie wurden gemergt und hinterliessen leere
Merge-Commits. Mit den zwei Folge-PRs, die aus demselben Grund gegenstandslos
waren, waren 16 der 59 PRs jenes Tages reine Reibung.

Dieselbe Klasse wie der handgeschriebene Stub, der denselben Feldnamen annahm
wie der Code: Nichts ist rot, weil nichts geprüft wird, worauf es ankommt.

## Teil 2 — dieses Repo

**ruff:** genau eine Quelle — das `[dev]`-Extra von `pyproject.toml`.
`pip install -e ".[dev]"` zieht die gepinnte Version, `ruff --version` zeigt
sie, und `scripts/check_ruff_pin.py` hält beides gegeneinander.
Keine zweite Version in die Workflows schreiben: ein solcher Schritt läuft
nach dem `[dev]`-Install und überstimmt den Pin still (`test_dependencies.py`
hält beides fest). Eine `.pre-commit-config.yaml` gibt es nicht.

**Die Nummer steht hier absichtlich nicht mehr**, und das ist an einem
Nachmittag zweimal teuer geworden. Hier stand `0.16.3`, während
`pyproject.toml` schon `0.16.4` pinnte — eine stille Drift, gefunden beim
Installieren nach dieser Zeile. Der naheliegende Handgriff war, die Zahl zu
korrigieren und einen Test daneben zu setzen, der sie gegen `pyproject.toml`
hält. Beides ging in #114 ein, und der nächste Dependabot-Bump
(0.16.4 → 0.16.5) kam **drei Minuten später** und machte mit diesem Test
`main` rot.

Der Fehler war nicht die Zahl, sondern die Kopie. Ein Gate, das verlangt, dass
ein handgepflegtes Literal einem automatischen Bump folgt, hat seinen
Fehlschlag im Normalbetrieb: Dependabot rührt diese Datei nicht an, also ist
jeder Routine-Bump ein roter Standard-Branch. Ein Gate, das bei jedem
gewöhnlichen Vorgang anspringt, wird abgeschaltet — und dann fehlt es dort,
wo es nötig wäre.

`scripts/check_version_sync.py` hat die Regel längst formuliert, nur für
`src/`: «ein wieder eingefügtes Literal wäre der Beginn derselben Drift». Für
diese Datei gilt sie genauso. Der Test heisst deshalb jetzt umgekehrt — er
prüft, dass hier **keine** Version wiederholt wird.

Vor dem Lauf `ruff --version` prüfen: ein älteres ruff früher im `PATH`
schlägt den Pin, ohne dass der Install etwas meldet.

**Gates, wörtlich aus der CI:**

```bash
python scripts/check_ruff_pin.py
ruff check src/ tests/ scripts/
ruff format --check src/ tests/ scripts/
python -m py_compile src/srgssr_mcp/server.py
python scripts/check_version_sync.py
python scripts/check_dependabot_labels.py
pytest -m "not live" --cov=src --cov-report=term-missing --cov-fail-under=80
```

**«Die CI» sind hier zwei Workflows.** Die ersten sechs Befehle stehen im Job
`quality` in `ci.yml`, der `pytest` allein im Job `test` in `test.yml` —
beide mit Matrix 3.11/3.12/3.13, beide auf `push`/`pull_request` gegen `main`.
Ein roter Check «CI» und ein roter Check «Tests» zeigen also auf verschiedene
Dateien; wer nach dem falschen sucht, findet nichts. In `test.yml` trägt der
`pytest` zusätzlich `--cov-report=xml` für den Upload danach — der Upload ist
auf 3.11 beschränkt und `continue-on-error: true`, also kein Gate. Das
Coverage-Minimum von 80 % ist eines: es steht im `pytest`-Aufruf selbst.

**Das Label-Gate steht, deklariert wird trotzdem nichts.**
`check_dependabot_labels.py` vergleicht, was `.github/dependabot.yml` unter
`labels:` verlangt, mit den Labels, die das Repo wirklich hat. Für einen
*deklarierten* Namen legt Dependabot nichts an, sondern kommentiert nur an
jedem PR und lässt ihn ungelabelt — kein roter Check, kein Log. Genau so ist es
hier gelaufen, die Meldung steht unter PR #48 vom 30.7.2026 und blieb einen
Monat liegen. In der CI kommt der Token aus `secrets.GITHUB_TOKEN`; fehlt er
dort, **fällt** der Schritt, statt zu überspringen — ein Gate, das ohne
Zugangsdaten durchwinkt, wäre die Attrappe, gegen die es gebaut ist. Lokal ohne
Token prüft es nur die Deklaration und sagt das ausdrücklich, ist also kein
Beleg.

**Die Deklaration selbst war der Fehler, nicht ihre Lücke.** PR #103 trug
`labels: ["dependencies"]` wieder ein und liess `github-actions` bewusst weg,
weil dieses Label hier gemessen nicht existiert (29.8.2026, 12:38 UTC:
`dependencies` als Treffer, `github-actions` als echtes «not found», mit
Positivkontrolle im selben Aufruf — die Methode dazu steht unter «Ein 403 ist
gar keine Auskunft» in Teil 1). Die Messung stimmt; der Schluss daraus nicht.
Das Ökosystem-Label fehlte, **weil** eine eigene Liste den Vorgabesatz ersetzt,
den Dependabot sonst selbst anlegt und pflegt. Die Abwesenheit war also die
Folge der Deklaration und nicht ihr Grund — dieselbe Umkehrung wie in Teil 1,
nur eine Ebene tiefer.

Seit diesem PR steht `labels:` deshalb in keinem der beiden Blöcke, und der
Ankertest sichert das zu. Ehrlicherweise heisst das: **das Gate prüft im
Moment nichts** — ohne Deklaration hat es keinen Namen abzugleichen. Es
bleibt trotzdem, weil es genau den Fall abfängt, der es nötig macht: sobald
jemand wieder eine Liste einträgt, wird ein fehlender Name dort ein roter
Check statt eines übersehenen Kommentars.

**`secret-scan.yml` gatet ebenfalls jeden PR** (gitleaks, gegen `main`) und
steht in keiner Liste — lokal stellt ihn keiner der Befehle oben nach. Ein
roter PR bei grünen Tests ist meistens er.

**`codex-gate.yml` gatet den Merge, nicht den Code.** Er prüft nichts am Diff,
sondern wartet, bis die Codex-Statustabelle des Bots für den aktuellen Head auf
`Completed` steht — die Begründung dazu steht unter «Wenn Codex gar nicht erst
hinsieht» in Teil 1, die Mechanik im Workflow selbst. Lokal ist er nicht
nachstellbar und gehört deshalb nicht in die Gate-Liste oben; er braucht einen
PR und die GitHub-API. Dass er den Merge wirklich hält, hängt an einem
Required-Check-Eintrag in der Branch Protection — der steht in keiner Datei
dieses Repos und ist beim Lesen des Workflows nicht zu sehen.

Kein `include` unter `[tool.ruff]` setzen. Es stand dort auf
`["src/**/*.py"]` und hob die Pfadangabe der beiden ruff-Gates still wieder
auf: sie liefen grün, während sie nur `src/` prüften (behoben in #68).

**Fixtures: der Recorder steht, die Aufzeichnungen fehlen noch.** Die Messung
vom 15.08.2026 stimmt — ohne Consumer Key antworten Token-Endpunkt und alle
fünf Produkt-Basen mit 401 —, aber die Schlussfolgerung daraus war zu weit.
Nachgemessen am 16.08.2026: die 401 kommt von SRG SSR selbst (eigene Header,
CONNECT geht durch), der Host ist also erreichbar und es fehlen allein die
Credentials. Die liegen längst da, wo der nächtliche Live-Lauf sie nimmt.
`.github/workflows/record-fixtures.yml` fährt `scripts/record_fixtures.py` mit
denselben Secrets, auf Knopfdruck.

Ein Recorder, den niemand fahren *und* niemand prüfen kann, wäre das plausibel
aussehende, unwiderlegbare Artefakt, gegen das die Konvention gerichtet ist.
Seine Mechanik hängt aber nicht an den Credentials:
`tests/test_record_fixtures.py` fährt ihn gegen eine gemockte API und prüft
Plan, Zuordnung, Kürzung, Nachweis — und vor allem den Token-Umgang.

**Das Token gehört in keine Datei.** Diese API ist die einzige im Portfolio mit
OAuth2. Die Antwort von `/oauth/v1/accesstoken` trägt ein gültiges
Bearer-Token, die Anfrage dorthin `Authorization: Basic <key:secret>`. Ein
Recorder, der «jede Antwort» ablegt, committet beim ersten Lauf ein
funktionierendes Token. Drei Riegel: die Token-URL ist ausgenommen, der
Schlüssel ist die URL ohne jeden Header, und vor dem Schreiben läuft eine
Prüfung gegen Token, Key und Secret, die **abbricht** statt zu warnen — eine
halb geschriebene Aufzeichnung ist wiederholbar, ein veröffentlichtes Token
nicht. Der Workflow prüft danach noch einmal, ausserhalb des Programms, das er
bewacht.

**`srf-meteo` drosselt hart.** Gemessen: der zweite Abruf auf dieselbe
Koordinate kommt mit HTTP 429 zurück und bleibt es über vier Retries. Vier
Werkzeuge lösen dieselbe Koordinate auf, der Recorder holt sie deshalb genau
einmal (`_EinmalHolen`) und pausiert zwischen den Plan-Einträgen. Wer den
Aufnahme-Workflow zweimal kurz hintereinander fährt, misst die Drosselung und
nicht die Quelle — nach einem roten Lauf erst warten, dann wiederholen.

Bis die Aufzeichnungen da sind, trägt der nächtliche Live-Lauf die Drift-Frage
— stärker als Fixtures, weil er die Quelle von heute prüft, aber nur solange er
*jedes* Werkzeug erreicht. Genau das hält `test_live_coverage.py` fest, samt
der Probe im Docstring.

**Live-Tests:** `.github/workflows/live-test.yml` läuft nächtlich per Cron
(`0 4 * * *`) plus `workflow_dispatch`, mit Credential-Guard vor dem Lauf; ein
roter Lauf öffnet ein Issue, der von Hand gestartete ebenso. Sie sind hier also
nicht bloss per `-m "not live"` ausgeschlossen.

**Der Cron sagt, worum er bittet — nicht, wann gelaufen wird.** Gemessen am
18.9.2026: Die vier vorangehenden `schedule`-Läufe wurden um 09:44, 09:18,
09:12 und 09:20 UTC erzeugt (14.–17.9.), also rund fünf Stunden nach der
deklarierten Zeit, und zwar jeder. Die naheliegende Ursache — GitHub verzögert
geplante Workflows unter Last — ist **nicht** gemessen; belegt sind die vier
Zeitstempel.

Hier stehen sie als Datum und nicht als gepflegter Wert: Eine Zeile «läuft
effektiv um 09:20» wäre die nächste Kopie, die driftet, und zwar gegen etwas,
das niemand steuert. Vier datierte Beobachtungen veralten nicht, sie werden
Geschichte.

`test_live_workflow_docs.py` fällt deshalb hier nicht ein — und das ist kein
Mangel des Tests, sondern seine Grenze: Er hält `0 4 * * *` gegen «04:00 UTC»
in beiden `CONTRIBUTING`-Dateien, also Deklaration gegen Deklaration. Die
tatsächliche Auslösezeit liegt bei GitHub und in keiner Datei dieses Repos.
Was daraus folgt, steht in beiden `CONTRIBUTING`-Dateien: aus dem Cron nicht
schliessen, dass der Lauf stattgefunden hat — die Lauf-Liste fragen. Der Workflow allein erfüllt
DRIFT-005 aber nicht — dazu gehört, Kadenz und Empfänger zu dokumentieren, und
das steht in `CONTRIBUTING.md`, gegen den Workflow gehalten von
`test_live_workflow_docs.py`.
