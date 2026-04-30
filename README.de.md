[🇬🇧 English Version](README.md)

> 🇨🇭 **Teil des [Swiss Public Data MCP Portfolios](https://github.com/malkreide)**

# 📺 srgssr-mcp

![Version](https://img.shields.io/badge/version-0.1.0-blue)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![MCP](https://img.shields.io/badge/MCP-Model%20Context%20Protocol-purple)](https://modelcontextprotocol.io/)
[![CI](https://github.com/malkreide/srgssr-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/malkreide/srgssr-mcp/actions)
[![Datenquelle](https://img.shields.io/badge/Daten-SRG%20SSR%20Public%20API-red)](https://developer.srgssr.ch)

> MCP-Server, der KI-Modelle mit den öffentlichen APIs der SRG SSR verbindet – Wetter, TV-/Radio-Metadaten, Programmguide und Schweizer Abstimmungen/Wahlen seit 1900 (SRF, RTS, RSI, RTR, SWI).

<p align="center">
  <img src="assets/demo.svg" alt="Demo: Claude stellt eine Frage → srgssr-mcp Tool Call → fundierte Antwort aus der SRG SSR Polis API" width="760">
</p>

---

## Übersicht

**srgssr-mcp** gibt KI-Assistenten wie Claude direkten Zugriff auf die öffentlichen APIs der SRG SSR – dem Schweizer öffentlich-rechtlichen Medienunternehmen. Wetterprognosen, TV- und Radio-Metadaten, elektronische Programmguides und historische Demokratie-Daten (Abstimmungen und Wahlen seit 1900) sind über eine einzige standardisierte MCP-Schnittstelle zugänglich.

Der Server deckt fünf thematische Cluster ab: SRF Wetter, Video, Audio, EPG und Polis (Schweizer Demokratie). Jeder Cluster entspricht einer Gruppe zweckgerichteter Tools, die Rohdaten der SRG SSR APIs in saubere JSON-Antworten übersetzen.

**Anker-Demo-Abfrage:** *«Was waren die Abstimmungsresultate zur Volksinitiative X im Kanton Zürich?»* – beantwortet mit historischen Echtzeit-Daten aus dem Polis-System, nicht mit einer Halluzination.

---

## Funktionen

- 🌦️ **Wetter** – Standortsuche, aktuelle Bedingungen, 24h-Stundenprognose, 7-Tages-Prognose (SRF Meteo)
- 📺 **Video** – TV-Sendungslisten, neueste Episoden, Live-TV-Kanäle aller Unternehmenseinheiten
- 🎙️ **Audio** – Radiosendungslisten, Audio-Episoden, Live-Radiostationen
- 📅 **EPG** – Tagesprogramm für jeden TV- oder Radiokanal
- 🗳️ **Polis** – Volksabstimmungen und Wahlen seit 1900, nationale und kantonale Resultate
- 🏢 **Multi-Unit** – SRF (DE), RTS (FR), RSI (IT), RTR (RM), SWI (mehrsprachig)
- 🔐 **OAuth2** – automatisches Token-Management mit Client Credentials Flow
- ☁️ **Dual Transport** – stdio für Claude Desktop, Streamable HTTP/SSE für Cloud-Deployment

---

## Voraussetzungen

- Python 3.11+
- **API-Schlüssel** von [developer.srgssr.ch](https://developer.srgssr.ch) (kostenlose Registrierung):
  1. Konto erstellen und anmelden
  2. Unter «My Apps» eine neue Applikation anlegen
  3. Produkt **SRG SSR PUBLIC API V2** hinzufügen
  4. **Consumer Key** und **Consumer Secret** notieren

> ⚠️ **Nutzungsbedingungen:** Die SRG SSR APIs sind für nicht-kommerzielle Nutzung freigegeben. Bei kommerzieller Nutzung direkt anfragen: [api@srgssr.ch](mailto:api@srgssr.ch)

---

## Installation

```bash
# Repository klonen
git clone https://github.com/malkreide/srgssr-mcp.git
cd srgssr-mcp

# Installieren
pip install -e .
```

Oder mit `uvx` (ohne dauerhafte Installation):

```bash
uvx srgssr-mcp
```

Oder via pip:

```bash
pip install srgssr-mcp
```

---

## Schnellstart

```bash
# Zugangsdaten setzen
export SRGSSR_CONSUMER_KEY="dein-consumer-key"
export SRGSSR_CONSUMER_SECRET="dein-consumer-secret"

# Server starten (stdio-Modus für Claude Desktop)
srgssr-mcp
```

Sofort in Claude Desktop ausprobieren:

> *«Wie wird das Wetter morgen in Zürich?»*
> *«Was läuft heute Abend auf SRF 1?»*
> *«Welche Volksabstimmungen gab es im Kanton Bern zwischen 2010 und 2020?»*

---

## Konfiguration

### Claude Desktop

**Minimal (empfohlen):**

```json
{
  "mcpServers": {
    "srgssr": {
      "command": "uvx",
      "args": ["srgssr-mcp"],
      "env": {
        "SRGSSR_CONSUMER_KEY": "dein-consumer-key",
        "SRGSSR_CONSUMER_SECRET": "dein-consumer-secret"
      }
    }
  }
}
```

**Pfad zur Konfigurationsdatei:**
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

Nach dem Speichern Claude Desktop vollständig neu starten.

### Andere MCP-Clients

Kompatibel mit Cursor, Windsurf, VS Code + Continue, LibreChat, Cline sowie selbst gehosteten Modellen via `mcp-proxy`. Gleiche Umgebungsvariablen setzen.

### Cloud-Deployment (SSE für Browser-Zugriff)

Für den Einsatz via **claude.ai im Browser** (z. B. auf verwalteten Arbeitsplätzen ohne lokale Software-Installation):

```bash
SRGSSR_CONSUMER_KEY=... SRGSSR_CONSUMER_SECRET=... \
  python -m srgssr_mcp.server --transport streamable_http --port 8000
```

> 💡 *«stdio für den Entwickler-Laptop, SSE für den Browser.»*

---

## MCP-Primitive

Dieser Server nutzt alle drei orthogonalen MCP-Primitive:

| Primitiv | Mentales Modell | Im Server vorhanden |
|---|---|---|
| **Tools** (Verben) | Ausführbare Funktionen / parametrisierte Abfragen | 15 Tools — Suche, Listen, Fetch, Aggregation |
| **Resources** (Substantive) | Passive, cache-freundliche Daten hinter URIs | EPG-Einträge und immutable Abstimmungsresultate |
| **Prompts** (Kochrezepte) | Wiederverwendbare Workflow-Templates | Abstimmungsanalyse & Tagesbriefing |

Tools decken parametrisierte Abfragen ab (Jahres-Ranges, Freitext, Paginierung), bei denen jeder Aufruf andere Resultate liefern kann. Resources exponieren stabile Datenpunkte, die clientseitig gecacht werden können: einen veröffentlichten EPG-Eintrag für einen Kanal/Tag oder das endgültige Resultat einer abgeschlossenen Schweizer Volksabstimmung. Prompts standardisieren wiederkehrende mehrstufige Analysen, damit User sie nicht jedes Mal neu formulieren müssen.

### Resources

| URI-Template | Beschreibung |
|---|---|
| `epg://{bu}/{channel_id}/{date}` | Tagesprogramm eines TV- oder Radiosenders (SRF, RTS, RSI) — z.B. `epg://srf/srf1/2026-04-30` |
| `votation://{votation_id}` | Detailresultat einer abgeschlossenen Schweizer Volksabstimmung — z.B. `votation://v1` |

### Prompts

| Name | Argumente | Zweck |
|---|---|---|
| `analyse_abstimmungsverhalten` | `votation_id`, `focus` (`stadt_land` / `sprachregionen` / `kantone`) | Strukturierte Analyse einer Schweizer Volksabstimmung |
| `tagesbriefing_kanton` | `location`, `channel_id`, `business_unit`, `date` | Tagesbriefing mit Wetter und Programm |

---

## Verfügbare Tools

### Tool-Namenskonvention

Dieser Server verwendet **`snake_case`** für Tool-Namen und folgt damit den Konventionen des Python-Ökosystems. Die MCP-Best-Practice bevorzugt zwar `camelCase` für optimale LLM-Tokenisierung, doch `snake_case` ist weiterhin akzeptabel und hält die Tool-Namen konsistent mit den zugrunde liegenden Python-Funktions-Bezeichnern.

Alle Tools folgen dem Schema `srgssr_<domain>_<action>` mit dem Namespace-Präfix `srgssr_` und einem semantisch aussagekräftigen `<domain>_<action>`-Suffix (z. B. `srgssr_weather_current`, `srgssr_polis_get_votations`).

### 🌦️ SRF Wetter (4 Tools)

| Tool | Beschreibung | Datenquelle |
|---|---|---|
| `srgssr_weather_search_location` | Standort nach Name oder PLZ suchen, `geolocationId` ermitteln | SRF Meteo |
| `srgssr_weather_current` | Aktuelles Wetter für einen Schweizer Standort | SRF Meteo |
| `srgssr_weather_forecast_24h` | Stündliche 24-Stunden-Prognose | SRF Meteo |
| `srgssr_weather_forecast_7day` | Tägliche 7-Tages-Prognose | SRF Meteo |

### 📺 Video (3 Tools)

| Tool | Beschreibung | Datenquelle |
|---|---|---|
| `srgssr_video_get_shows` | TV-Sendungen einer Unternehmenseinheit auflisten | SRG SSR IL |
| `srgssr_video_get_episodes` | Neueste Episoden einer Sendung abrufen | SRG SSR IL |
| `srgssr_video_get_livestreams` | Live-TV-Kanäle auflisten | SRG SSR IL |

### 🎙️ Audio (3 Tools)

| Tool | Beschreibung | Datenquelle |
|---|---|---|
| `srgssr_audio_get_shows` | Radiosendungen einer Unternehmenseinheit auflisten | SRG SSR IL |
| `srgssr_audio_get_episodes` | Audio-Episoden einer Sendung abrufen | SRG SSR IL |
| `srgssr_audio_get_livestreams` | Live-Radiostationen auflisten | SRG SSR IL |

### 📅 EPG – Electronic Program Guide (1 Tool)

| Tool | Beschreibung | Datenquelle |
|---|---|---|
| `srgssr_epg_get_programs` | Tagesprogramm für einen TV- oder Radiosender abrufen | SRG SSR IL |

### 🗳️ Polis – Schweizer Demokratie (3 Tools)

| Tool | Beschreibung | Datenquelle |
|---|---|---|
| `srgssr_polis_get_votations` | Volksabstimmungen seit 1900 (national oder kantonal) | Polis API |
| `srgssr_polis_get_votation_results` | Detaillierte Resultate einer Abstimmung | Polis API |
| `srgssr_polis_get_elections` | Wahlergebnisse seit 1900 | Polis API |

### Unterstützte Unternehmenseinheiten

| Kürzel | Einheit | Sprache |
|---|---|---|
| `srf` | SRF (Schweizer Radio und Fernsehen) | Deutsch |
| `rts` | RTS (Radio Télévision Suisse) | Französisch |
| `rsi` | RSI (Radiotelevisione svizzera) | Italienisch |
| `rtr` | RTR (Radiotelevisiun Svizra Rumantscha) | Rätoromanisch |
| `swi` | SWI swissinfo.ch | Mehrsprachig |

### Beispiel-Abfragen

| Abfrage | Tool |
|---|---|
| *«Wetter in Zürich morgen?»* | `srgssr_weather_forecast_24h` |
| *«Was läuft heute auf SRF 1?»* | `srgssr_epg_get_programs` |
| *«Neueste Tagesschau-Episoden?»* | `srgssr_video_get_episodes` |
| *«Volksabstimmungen im Kanton Bern 2010–2020?»* | `srgssr_polis_get_votations` |
| *«Kantonale Resultate zur Maskeninitiative?»* | `srgssr_polis_get_votation_results` |
| *«Alle aktuellen RTS-Radiosendungen?»* | `srgssr_audio_get_shows` |

→ [Weitere Anwendungsbeispiele nach Zielgruppe](EXAMPLES.md) →

---

## Architektur

```
┌─────────────┐
│ Claude / LLM│
└──────┬──────┘
       │ MCP (stdio)
┌──────▼───────────────────┐
│ srgssr-mcp Server        │
│  ├─ Wetter-Tools (4)     │
│  ├─ EPG-Tools (1)        │
│  ├─ Polis-Tools (3)      │
│  ├─ Video-Tools (3)      │
│  └─ Audio-Tools (3)      │
└──────┬───────────────────┘
       │ HTTPS (OAuth2)
┌──────▼──────────────┐
│ SRG SSR Public APIs │
│  developer.srgssr.ch│
└─────────────────────┘
```

### Datenquellen

| Quelle | Daten | Zugang |
|---|---|---|
| [developer.srgssr.ch](https://developer.srgssr.ch) | SRG SSR PUBLIC API V2 (Wetter, A/V, EPG, Polis) | OAuth2 (kostenlose Registrierung) |

**Quellenangabe:** Die SRG SSR APIs unterliegen den [Nutzungsbedingungen der SRG SSR](https://developer.srgssr.ch).

---

## MCP Protocol Version

Dieser Server wird gegen die MCP-Protokollversion **`2025-06-18`** entwickelt und getestet.

Die Version ist als Konstante `PROTOCOL_VERSION` in [`src/srgssr_mcp/_app.py`](src/srgssr_mcp/_app.py) explizit gepinnt und wird beim Import gegen die `SUPPORTED_PROTOCOL_VERSIONS` des installierten SDK validiert — ein `fastmcp`/`mcp`-Upgrade, das die gepinnte Spec-Revision fallen lässt, schlägt sofort beim Start fehl, statt still die Wire-Semantik zu ändern. Spec-Bumps werden in [CHANGELOG.md](CHANGELOG.md) unter dem jeweiligen Release dokumentiert.

### Update-Policy

- SDK-Dependency-Updates kommen via Dependabot (`.github/dependabot.yml`, monatlich, gruppiert unter dem Label `mcp-sdk`) und müssen die komplette Testsuite passieren, bevor sie gemerged werden.
- Spec-Bumps werden auf einem Feature-Branch gegen das passende MCP-SDK-Release evaluiert; die [offizielle MCP-Changelog](https://modelcontextprotocol.io/specification/draft/changelog) ist Quelle der Wahrheit für Breaking Changes.
- Jeder Spec-Version-Bump landet im `CHANGELOG.md` und löst — falls sich der nach aussen sichtbare Wire-Contract ändert — einen Minor- oder Major-Release gemäss [Semantic Versioning](https://semver.org/) aus.

---

## Projektstruktur

```
srgssr-mcp/
├── src/srgssr_mcp/
│   ├── __init__.py          # Paket
│   └── server.py            # FastMCP-Server: 14 Tools, OAuth2-Client
├── .github/
│   └── workflows/
│       └── ci.yml           # GitHub Actions CI (Python 3.11–3.13)
├── pyproject.toml           # Build-Konfiguration (hatchling)
├── CHANGELOG.md
├── CONTRIBUTING.md          # Englisch
├── CONTRIBUTING.de.md       # Deutsch
├── LICENSE                  # MIT
├── README.md                # Englische Hauptversion
└── README.de.md             # Diese Datei (Deutsch)
```

---

## 🛡️ Sicherheit & Limits

| Aspekt | Details |
|--------|---------|
| **Zugriff** | Nur lesend — der Server liest ausschliesslich aus SRG SSR APIs und kann keine Inhalte posten, ändern oder löschen |
| **Personendaten** | Keine Personendaten — alle Endpoints liefern öffentliche Sendungs-Metadaten, Wetterdaten sowie historische Abstimmungs- und Wahlresultate |
| **Rate Limits** | Abhängig von der Stufe deiner OAuth2-Applikation auf [developer.srgssr.ch](https://developer.srgssr.ch); der Server ergänzt sinnvolle Pro-Query-Caps (z.B. max. 100 Episoden, 50 Sendungen pro Listen-Call) |
| **Timeout** | 30 Sekunden pro Upstream-API-Call |
| **Authentifizierung** | OAuth2 Client Credentials (kostenlose Registrierung); Secrets bleiben lokal, werden nicht geloggt |
| **Lizenz & Nutzung** | Die SRG SSR APIs sind für **nicht-kommerzielle Nutzung** vorgesehen; kommerzielle Nutzung erfordert schriftliche Genehmigung via [api@srgssr.ch](mailto:api@srgssr.ch) |
| **Nutzungsbedingungen** | Es gelten die [SRG SSR Developer Terms of Use](https://developer.srgssr.ch) — Nutzende bleiben für Quellenangabe und Compliance verantwortlich |

---

## Bekannte Limits

- **Rate Limits:** SRG SSR APIs haben Rate-Limits — Details bei [developer.srgssr.ch](https://developer.srgssr.ch) je nach Stufe der OAuth2-Applikation
- **Data Freshness:** EPG-Daten sind bis zu 6 Stunden verzögert
- **Historical Data:** Polis-Daten reichen bis 1900, ältere Daten nicht verfügbar
- **Geo-Restriction:** Einige Streaming-APIs nur in der Schweiz verfügbar
- **API-Keys erforderlich:** SRG SSR APIs erfordern kostenlose OAuth2-Zugangsdaten von [developer.srgssr.ch](https://developer.srgssr.ch)
- **Nicht-kommerzielle Nutzung:** Die SRG SSR API-Bedingungen beschränken die kommerzielle Nutzung ohne explizite Genehmigung von [api@srgssr.ch](mailto:api@srgssr.ch)
- **Wetterdaten:** SRF Meteo deckt nur die Schweiz ab

---

## Tests

```bash
# Unit-Tests (kein Netzwerk erforderlich)
PYTHONPATH=src pytest tests/ -m "not live"

# Integrationstests (erfordern SRG SSR API-Keys)
PYTHONPATH=src pytest tests/ -m "live"

# Linting
ruff check src/
```

---

## Beitragen

Siehe [CONTRIBUTING.md](CONTRIBUTING.md) (Englisch) · [CONTRIBUTING.de.md](CONTRIBUTING.de.md) (Deutsch)

---

## Changelog

Siehe [CHANGELOG.md](CHANGELOG.md)

---

## Lizenz

MIT-Lizenz – siehe [LICENSE](LICENSE)

Die verwendeten SRG SSR APIs unterliegen den [Nutzungsbedingungen der SRG SSR](https://developer.srgssr.ch).

---

## Autor

Hayal Oezkan · [github.com/malkreide](https://github.com/malkreide)

---

## Credits & Verwandte Projekte

- **Daten:** [SRG SSR Developer Portal](https://developer.srgssr.ch) · SRF Meteo · Polis API
- **Protokoll:** [Model Context Protocol](https://modelcontextprotocol.io/) – Anthropic / Linux Foundation
- **Verwandt:**

| Server | Beschreibung |
|---|---|
| [zurich-opendata-mcp](https://github.com/malkreide/zurich-opendata-mcp) | Stadt Zürich Open Data (OSTLUFT Luftqualität, Wetter, Parking, Geodaten) |
| [swiss-transport-mcp](https://github.com/malkreide/swiss-transport-mcp) | OJP 2.0 Reiseplanung, SIRI-SX Störungen |
| [swiss-environment-mcp](https://github.com/malkreide/swiss-environment-mcp) | BAFU Umweltdaten – Luftqualität, Hydrologie, Naturgefahren |
| [swiss-statistics-mcp](https://github.com/malkreide/swiss-statistics-mcp) | BFS STAT-TAB – 682 Statistik-Datensätze |
| [fedlex-mcp](https://github.com/malkreide/fedlex-mcp) | Schweizer Bundesrecht via Fedlex SPARQL |

**Synergiebeispiel:** *«Was waren die Resultate der Volksabstimmungen 2020 im Kanton Zürich – und wie lag die Stimmbeteiligung im nationalen Vergleich?»*
→ `srgssr-mcp` (Polis, kantonale Resultate) + `swiss-statistics-mcp` (BFS, Stimmbeteiligung)

- **Portfolio:** [Swiss Public Data MCP Portfolio](https://github.com/malkreide)
