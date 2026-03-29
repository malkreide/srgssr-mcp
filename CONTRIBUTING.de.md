# Beitragen zu srgssr-mcp

Danke für dein Interesse, zu diesem Projekt beizutragen! Dieser MCP-Server ist Teil des [Swiss Public Data MCP Portfolios](https://github.com/malkreide) und folgt den gemeinsamen Konventionen des Portfolios.

[🇬🇧 English Version](CONTRIBUTING.md)

---

## Inhaltsverzeichnis

- [Fehler melden](#fehler-melden)
- [Entwicklungsumgebung einrichten](#entwicklungsumgebung-einrichten)
- [Änderungen vornehmen](#änderungen-vornehmen)
- [Code-Stil](#code-stil)
- [Tests](#tests)
- [Pull Request einreichen](#pull-request-einreichen)
- [Datenquellen & Quellenangabe](#datenquellen--quellenangabe)

---

## Fehler melden

Bitte prüfe vor dem Öffnen eines Issues die [bestehenden Issues](https://github.com/malkreide/srgssr-mcp/issues), um Duplikate zu vermeiden.

Beim Melden eines Fehlers bitte angeben:

- Eine klare Beschreibung des Problems
- Schritte zur Reproduktion
- Erwartetes vs. tatsächliches Verhalten
- Python-Version und Betriebssystem
- Relevante Fehlermeldungen oder Logs

Bei API-bezogenen Problemen (z. B. Endpunkt-Änderungen bei developer.srgssr.ch) ist zu beachten, dass dieser Server von externen SRG SSR APIs abhängt, die sich ohne Vorankündigung ändern können.

---

## Entwicklungsumgebung einrichten

```bash
# 1. Repository klonen
git clone https://github.com/malkreide/srgssr-mcp.git
cd srgssr-mcp

# 2. Im bearbeitbaren Modus mit Dev-Abhängigkeiten installieren
pip install -e ".[dev]"

# 3. API-Zugangsdaten setzen
export SRGSSR_CONSUMER_KEY="dein-consumer-key"
export SRGSSR_CONSUMER_SECRET="dein-consumer-secret"

# 4. Serverstart überprüfen
python -m srgssr_mcp.server
```

**Voraussetzungen:**
- Python 3.11+
- API-Keys von [developer.srgssr.ch](https://developer.srgssr.ch) (kostenlose Registrierung, für Live-Tests erforderlich)

---

## Änderungen vornehmen

1. **Fork** des Repositories erstellen und einen Feature-Branch anlegen:
   ```bash
   git checkout -b feat/dein-feature-name
   ```

2. Format für [Conventional Commits](https://www.conventionalcommits.org/) einhalten:

   | Typ | Verwendung |
   |---|---|
   | `feat` | Neues Tool oder neue Funktionalität |
   | `fix` | Fehlerbehebung |
   | `docs` | Nur Dokumentation |
   | `refactor` | Code-Umstrukturierung ohne Verhaltensänderung |
   | `test` | Tests hinzufügen oder aktualisieren |
   | `chore` | Build, Abhängigkeiten, CI |

3. `CHANGELOG.md` unter `[Unreleased]` für jede benutzerseitig sichtbare Änderung aktualisieren.

4. Bei einem neuen Tool müssen sowohl `README.md` (Englisch) als auch `README.de.md` (Deutsch) aktualisiert werden.

---

## Code-Stil

Dieses Projekt verwendet [Ruff](https://docs.astral.sh/ruff/) für Linting und Formatierung.

```bash
# Auf Linting-Probleme prüfen
ruff check src/

# Wo möglich automatisch beheben
ruff check src/ --fix

# Code formatieren
ruff format src/
```

Die CI-Pipeline führt Ruff bei jedem Push aus – PRs mit Linting-Fehlern werden nicht gemergt.

**Allgemeine Konventionen:**
- Type Hints für alle öffentlichen Funktionen
- Pydantic v2 für Datenvalidierung
- `httpx` für asynchrone HTTP-Aufrufe
- Aussagekräftige Tool-Beschreibungen (sie werden vom KI-Modell gelesen)

---

## Tests

```bash
# Nur Unit-Tests (kein Netzwerk erforderlich)
PYTHONPATH=src pytest tests/ -m "not live"

# Integrationstests (erfordern SRG SSR API-Keys)
PYTHONPATH=src pytest tests/ -m "live"

# Vollständige Testsuite
PYTHONPATH=src pytest tests/
```

Tests werden mit `@pytest.mark.live` markiert, wenn sie externe APIs aufrufen. Die CI-Pipeline führt nur Nicht-Live-Tests aus, um Instabilität durch externe Abhängigkeiten zu vermeiden.

Bei einem neuen Tool bitte mindestens einen Unit-Test und einen Live-Integrationstest hinzufügen.

---

## Pull Request einreichen

1. Sicherstellen, dass alle Tests bestehen und Ruff keine Fehler meldet
2. `CHANGELOG.md` aktualisieren
3. Branch pushen und Pull Request gegen `main` öffnen
4. Beschreiben, was geändert wurde und warum – verwandte Issues verlinken

PRs, die Breaking Changes an bestehenden Tool-Signaturen einführen, erfordern zuerst eine Diskussion.

---

## Datenquellen & Quellenangabe

Dieser Server verwendet die SRG SSR Public API V2:

| Quelle | Anbieter | Nutzungsbedingungen |
|---|---|---|
| [developer.srgssr.ch](https://developer.srgssr.ch) | SRG SSR | Kostenlos für nicht-kommerzielle Nutzung, OAuth2 erforderlich |

Die SRG SSR APIs unterliegen den [Nutzungsbedingungen der SRG SSR](https://developer.srgssr.ch). Beiträge, die weitere Datenquellen einbinden, müssen deren Lizenz- und Quellenangabepflichten hier dokumentieren.

---

## Portfolio-Kontext

Dieser Server ist Teil eines kohärenten Portfolios von Schweizer Open-Data-MCP-Servern. Beim Beitragen bitte beachten:

- **Graceful Degradation**: Der Server soll auch dann starten und Teilfunktionalität bieten, wenn einzelne APIs nicht erreichbar sind
- **Bilinguale Dokumentation**: Benutzerseitige Dokumentationsänderungen müssen in `README.md` (Englisch) und `README.de.md` (Deutsch) übernommen werden
- **Konsistente Benennung**: Tool-Namen folgen der `srgssr_`-Prefix-Konvention

---

Fragen? Ein [GitHub Discussion](https://github.com/malkreide/srgssr-mcp/discussions) eröffnen oder ein Issue erstellen.
