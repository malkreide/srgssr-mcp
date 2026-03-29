# Changelog

## [0.1.0] - 2026-03-29

### Added
- Initial release
- 12 Tools für SRG SSR APIs: SRF Wetter (4), Video (3), Audio (3), EPG (1), Polis/Demokratie (3)
- Unterstützung für SRF, RTS, RSI, RTR, SWI
- Historische Abstimmungs- und Wahldaten seit 1900 via Polis-API
- OAuth2-Authentifizierung für SRG SSR Developer APIs
- Dual-Transport: stdio (lokal) + Streamable HTTP (Cloud)
```

3. Commit-Nachricht: `docs: update CHANGELOG for v0.1.0`

### 3.2 Release auf GitHub erstellen

1. Gehe zu `https://github.com/malkreide/srgssr-mcp/releases`
2. Klicke **"Draft a new release"**
3. Fülle aus:

| Feld | Wert |
|------|------|
| **Tag** | `v0.1.0` — wähle "Create new tag on publish" |
| **Target branch** | `main` |
| **Release title** | `v0.1.0 — Initial Release` |
| **Description** | Inhalt aus CHANGELOG einfügen |

4. Klicke **"Publish release"** (nicht "Save draft"!)

### 3.3 Was jetzt passiert (automatisch)
```
Release "Published"
        │
        ▼
publish.yml wird ausgelöst
        │
        ├── Job "build": baut Wheel + sdist
        │
        └── Job "publish": sendet dist/ an PyPI
                  │
                  ├── GitHub generiert OIDC-Token
                  ├── PyPI prüft: stimmt mit Pending Publisher überein?
                  └── ✅ Paket wird veröffentlicht als "srgssr-mcp 0.1.0"

## [1.0.0] – 2025-03-08

### Neu / Added
- SRF Wetter: Standortsuche, aktuelles Wetter, 24h-Prognose, 7-Tages-Prognose
- Video-API: Sendungsliste, Episoden, Live-TV-Kanäle (SRF, RTS, RSI, RTR, SWI)
- Audio-API: Sendungsliste, Episoden, Live-Radiostationen
- EPG: Tagesprogramm-Abruf für TV und Radio
- Polis: Volksabstimmungen und Wahlen seit 1900
- OAuth2 Client Credentials mit automatischem Token-Caching
- Dual-Transport: stdio (lokal) + Streamable HTTP (Cloud)
- Zweisprachige Dokumentation (Deutsch/Englisch)
- Paginierungsunterstützung für alle Listen-Tools
