# srgssr-mcp

**[🇬🇧 English version](README_EN.md)**

Ein [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) Server, der KI-Modellen Zugang zu den öffentlichen APIs der SRG SSR ermöglicht – dem Schweizer öffentlich-rechtlichen Medienunternehmen (SRF, RTS, RSI, RTR, SWI).

> **Anker-Beispiel:** Eine Frage wie «Was waren die Abstimmungsresultate zur Volksinitiative X im Kanton Zürich?» wird mit historischen Echtzeit-Daten aus dem Polis-System beantwortet – nicht mit einer Halluzination.

---

## Verfügbare Tools (12)

### 🌦️ SRF Wetter (4 Tools)

| Tool | Beschreibung |
|---|---|
| `srgssr_weather_search_location` | Standort nach Name oder PLZ suchen, `geolocationId` ermitteln |
| `srgssr_weather_current` | Aktuelles Wetter für einen Schweizer Standort |
| `srgssr_weather_forecast_24h` | Stündliche 24-Stunden-Prognose |
| `srgssr_weather_forecast_7day` | Tägliche 7-Tages-Prognose |

### 📺 Video (3 Tools)

| Tool | Beschreibung |
|---|---|
| `srgssr_video_get_shows` | TV-Sendungen einer Unternehmenseinheit auflisten |
| `srgssr_video_get_episodes` | Neueste Episoden einer Sendung abrufen |
| `srgssr_video_get_livestreams` | Live-TV-Kanäle auflisten |

### 🎙️ Audio (3 Tools)

| Tool | Beschreibung |
|---|---|
| `srgssr_audio_get_shows` | Radiosendungen auflisten |
| `srgssr_audio_get_episodes` | Audio-Episoden einer Sendung abrufen |
| `srgssr_audio_get_livestreams` | Live-Radiostationen auflisten |

### 📅 EPG – Electronic Program Guide (1 Tool)

| Tool | Beschreibung |
|---|---|
| `srgssr_epg_get_programs` | Tagesprogramm für einen TV- oder Radiosender abrufen |

### 🗳️ Polis – Schweizer Demokratie (3 Tools)

| Tool | Beschreibung |
|---|---|
| `srgssr_polis_get_votations` | Volksabstimmungen seit 1900 (national oder kantonal) |
| `srgssr_polis_get_votation_results` | Detaillierte Resultate einer Abstimmung |
| `srgssr_polis_get_elections` | Wahlergebnisse seit 1900 |

---

## Unterstützte Unternehmenseinheiten

| Kürzel | Einheit | Sprache |
|---|---|---|
| `srf` | SRF (Schweizer Radio und Fernsehen) | Deutsch |
| `rts` | RTS (Radio Télévision Suisse) | Französisch |
| `rsi` | RSI (Radiotelevisione svizzera) | Italienisch |
| `rtr` | RTR (Radiotelevisiun Svizra Rumantscha) | Rätoromanisch |
| `swi` | SWI swissinfo.ch | Mehrsprachig |

---

## Voraussetzungen

### API-Schlüssel

Kostenlose Registrierung auf [developer.srgssr.ch](https://developer.srgssr.ch):

1. Konto erstellen und anmelden
2. Unter «My Apps» eine neue Applikation anlegen
3. Produkt **SRG SSR PUBLIC API V2** hinzufügen
4. **Consumer Key** und **Consumer Secret** notieren

> ⚠️ **Nutzungsbedingungen:** Die SRG SSR APIs sind für nicht-kommerzielle Nutzung freigegeben. Bei kommerzieller Nutzung direkt anfragen: [api@srgssr.ch](mailto:api@srgssr.ch)

### Python

Python 3.11 oder neuer.

---

## Installation und Konfiguration

### Claude Desktop

Konfigurationsdatei öffnen:

- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

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

Claude Desktop vollständig neu starten.

### Andere MCP-Clients

Kompatibel mit Cursor, Windsurf, VS Code + Continue, LibreChat, Cline sowie selbst gehosteten Modellen via `mcp-proxy`. Gleiche Umgebungsvariablen setzen:

```bash
export SRGSSR_CONSUMER_KEY="dein-consumer-key"
export SRGSSR_CONSUMER_SECRET="dein-consumer-secret"
```

### SSE-Transport (Cloud / Render.com)

```bash
SRGSSR_CONSUMER_KEY=... SRGSSR_CONSUMER_SECRET=... \
  python -m srgssr_mcp.server --transport streamable_http --port 8000
```

---

## Beispiel-Anfragen

```
«Wie wird das Wetter morgen in Zürich?»
«Was läuft heute Abend auf SRF 1?»
«Zeige mir die neuesten Tagesschau-Episoden.»
«Welche Volksabstimmungen gab es im Kanton Bern zwischen 2010 und 2020?»
«Was waren die kantonalen Ergebnisse zur Abstimmung über die Maskeninitiative?»
«Liste alle aktuellen RTS-Radiosendungen auf.»
```

---

## Projektstruktur

```
srgssr-mcp/
├── src/
│   └── srgssr_mcp/
│       ├── __init__.py
│       └── server.py          # Alle 12 Tools
├── .github/
│   └── workflows/
│       └── ci.yml             # Ruff + Syntax-Check, Python 3.11–3.13
├── CHANGELOG.md
├── LICENSE                    # MIT
├── README.md                  # Diese Datei (Deutsch)
├── README_EN.md               # Englische Version
├── claude_desktop_config.json # Konfigurations-Vorlage
└── pyproject.toml
```

---

## Entwicklung

```bash
git clone https://github.com/malkreide/srgssr-mcp
cd srgssr-mcp
pip install -e ".[dev]"

# Syntax prüfen
python -m py_compile src/srgssr_mcp/server.py

# Linting
ruff check src/

# MCP Inspector (interaktives Testen)
npx @modelcontextprotocol/inspector uvx srgssr-mcp
```

---

## Verwandte Projekte

- [zurich-opendata-mcp](https://github.com/malkreide/zurich-opendata-mcp) – Stadtdaten Zürich (CKAN, Wetter, Luftqualität, Parkplätze, Gemeinderat)
- [fedlex-mcp](https://github.com/malkreide/fedlex-mcp) – Schweizer Bundesrecht via Fedlex SPARQL
- [swiss-transport-mcp](https://github.com/malkreide/swiss-transport-mcp) – Öffentlicher Verkehr Schweiz (OJP, SIRI-SX, Fahrpreise)

---

## Lizenz

MIT License – © 2025 [malkreide](https://github.com/malkreide)

Die verwendeten SRG SSR APIs unterliegen den [Nutzungsbedingungen der SRG SSR](https://developer.srgssr.ch).
