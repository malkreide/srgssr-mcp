# srgssr-mcp

**[🇩🇪 Deutsche Version](README.md)**

A [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server providing AI models with access to the public APIs of SRG SSR — Switzerland's national public broadcaster (SRF, RTS, RSI, RTR, SWI).

> **Example:** A question like "What were the cantonal results of the popular vote on initiative X?" is answered with historical data from the Polis system — not with a hallucination.

---

## Available Tools (12)

### 🌦️ SRF Weather (4 Tools)

| Tool | Description |
|---|---|
| `srgssr_weather_search_location` | Search for a Swiss location by name or postal code to obtain a `geolocationId` |
| `srgssr_weather_current` | Current weather conditions for a Swiss location |
| `srgssr_weather_forecast_24h` | Hourly 24-hour forecast |
| `srgssr_weather_forecast_7day` | Daily 7-day forecast |

### 📺 Video (3 Tools)

| Tool | Description |
|---|---|
| `srgssr_video_get_shows` | List TV shows for a business unit |
| `srgssr_video_get_episodes` | Retrieve latest episodes of a show |
| `srgssr_video_get_livestreams` | List live TV channels |

### 🎙️ Audio (3 Tools)

| Tool | Description |
|---|---|
| `srgssr_audio_get_shows` | List radio shows |
| `srgssr_audio_get_episodes` | Retrieve audio episodes of a show |
| `srgssr_audio_get_livestreams` | List live radio stations |

### 📅 EPG – Electronic Program Guide (1 Tool)

| Tool | Description |
|---|---|
| `srgssr_epg_get_programs` | Retrieve the daily program schedule for a TV or radio channel |

### 🗳️ Polis – Swiss Democracy (3 Tools)

| Tool | Description |
|---|---|
| `srgssr_polis_get_votations` | Popular votes since 1900 (national or cantonal) |
| `srgssr_polis_get_votation_results` | Detailed results of a specific vote |
| `srgssr_polis_get_elections` | Election results since 1900 |

---

## Supported Business Units

| Code | Unit | Language |
|---|---|---|
| `srf` | SRF (Schweizer Radio und Fernsehen) | German |
| `rts` | RTS (Radio Télévision Suisse) | French |
| `rsi` | RSI (Radiotelevisione svizzera) | Italian |
| `rtr` | RTR (Radiotelevisiun Svizra Rumantscha) | Romansh |
| `swi` | SWI swissinfo.ch | Multilingual |

---

## Prerequisites

### API Key

Free registration at [developer.srgssr.ch](https://developer.srgssr.ch):

1. Create an account and log in
2. Under "My Apps", create a new application
3. Add the product **SRG SSR PUBLIC API V2**
4. Note your **Consumer Key** and **Consumer Secret**

> ⚠️ **Terms of use:** SRG SSR APIs are available for non-commercial use. For commercial use, contact [api@srgssr.ch](mailto:api@srgssr.ch) directly.

### Python

Python 3.11 or newer.

---

## Installation and Configuration

### Claude Desktop

Open the configuration file:

- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "srgssr": {
      "command": "uvx",
      "args": ["srgssr-mcp"],
      "env": {
        "SRGSSR_CONSUMER_KEY": "your-consumer-key",
        "SRGSSR_CONSUMER_SECRET": "your-consumer-secret"
      }
    }
  }
}
```

Fully restart Claude Desktop.

### Other MCP Clients

Compatible with Cursor, Windsurf, VS Code + Continue, LibreChat, Cline, and self-hosted models via `mcp-proxy`. Set the same environment variables:

```bash
export SRGSSR_CONSUMER_KEY="your-consumer-key"
export SRGSSR_CONSUMER_SECRET="your-consumer-secret"
```

### SSE Transport (Cloud / Render.com)

```bash
SRGSSR_CONSUMER_KEY=... SRGSSR_CONSUMER_SECRET=... \
  python -m srgssr_mcp.server --transport streamable_http --port 8000
```

---

## Example Queries

```
"What will the weather be like in Zurich tomorrow?"
"What's on SRF 1 tonight?"
"Show me the latest Tagesschau episodes."
"Which popular votes took place in the canton of Bern between 2010 and 2020?"
"What were the cantonal results for the vote on the mask initiative?"
"List all current RTS radio shows."
```

---

## Project Structure

```
srgssr-mcp/
├── src/
│   └── srgssr_mcp/
│       ├── __init__.py
│       └── server.py          # All 12 tools
├── .github/
│   └── workflows/
│       └── ci.yml             # Ruff + syntax check, Python 3.11–3.13
├── CHANGELOG.md
├── LICENSE                    # MIT
├── README.md                  # German version
├── README_EN.md               # This file (English)
├── claude_desktop_config.json # Configuration template
└── pyproject.toml
```

---

## Development

```bash
git clone https://github.com/malkreide/srgssr-mcp
cd srgssr-mcp
pip install -e ".[dev]"

# Check syntax
python -m py_compile src/srgssr_mcp/server.py

# Linting
ruff check src/

# MCP Inspector (interactive testing)
npx @modelcontextprotocol/inspector uvx srgssr-mcp
```

---

## Related Projects

- [zurich-opendata-mcp](https://github.com/malkreide/zurich-opendata-mcp) – City of Zurich open data (CKAN, weather, air quality, parking, city council)
- [fedlex-mcp](https://github.com/malkreide/fedlex-mcp) – Swiss federal law via Fedlex SPARQL
- [swiss-transport-mcp](https://github.com/malkreide/swiss-transport-mcp) – Swiss public transport (OJP, SIRI-SX, fares)

---

## License

MIT License – © 2025 [malkreide](https://github.com/malkreide)

The SRG SSR APIs used in this project are subject to the [SRG SSR Terms of Use](https://developer.srgssr.ch).
