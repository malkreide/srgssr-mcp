# Contributing

Beiträge zu **srgssr-mcp** sind willkommen! Hier findest du die wichtigsten Informationen.

## Voraussetzungen

- Python 3.11+
- Ein API-Schlüssel von [developer.srgssr.ch](https://developer.srgssr.ch) (für Live-Tests)

## Entwicklungsumgebung einrichten

```bash
git clone https://github.com/malkreide/srgssr-mcp
cd srgssr-mcp
pip install -e ".[dev]"
```

## Code-Qualität

Vor jedem Commit bitte prüfen:

```bash
# Linting
ruff check src/

# Syntax-Check
python -m py_compile src/srgssr_mcp/server.py

# Tests
pytest -m "not live"
```

Wir verwenden [Ruff](https://docs.astral.sh/ruff/) mit einer Zeilenlänge von 120 Zeichen.

## Pull Requests

1. Fork erstellen und einen Feature-Branch anlegen (`git checkout -b feature/mein-feature`)
2. Änderungen committen mit einer aussagekräftigen Commit-Nachricht
3. Sicherstellen, dass Linting und Tests bestanden werden
4. Pull Request gegen `main` öffnen

## Neue Tools hinzufügen

Alle MCP-Tools befinden sich in `src/srgssr_mcp/server.py`. Beim Hinzufügen eines neuen Tools:

1. Tool-Funktion mit `@mcp.tool()` dekorieren
2. Klare Docstrings mit Parameterbeschreibungen schreiben
3. Die SRG SSR API-Dokumentation auf [developer.srgssr.ch](https://developer.srgssr.ch) beachten
4. README.md und README_EN.md aktualisieren

## Bugs melden

Bitte ein [Issue](https://github.com/malkreide/srgssr-mcp/issues) eröffnen mit:

- Beschreibung des Problems
- Schritte zur Reproduktion
- Erwartetes vs. tatsächliches Verhalten

## Lizenz

Mit deinem Beitrag stimmst du zu, dass er unter der [MIT-Lizenz](LICENSE) veröffentlicht wird.
