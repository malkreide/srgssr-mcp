# Finding: ARCH-005 — Keine Hardcoded Secrets

| Feld | Wert |
|---|---|
| **Severity** | critical |
| **Status** | open |
| **Server** | `srgssr-mcp` |
| **Check-Reference** | `ARCH-005` |
| **Audit-Datum** | 2026-05-06 |
| **Auditor** | Claude (mcp-audit-skill v0.5.0) |

## Observed Behavior

Pydantic-Settings-Pattern korrekt aufgesetzt: kein Klartext-Secret im Quellcode, `.env`-File nicht im Repo. Aber drei Secret-Hygiene-Lücken:

1. `consumer_secret: str` in `src/srgssr_mcp/config.py:30` ist als `str` typisiert, nicht als `pydantic.SecretStr` → akzidentielles Logging des Settings-Objekts würde den Secret als Klartext enthalten.
2. `.gitignore` enthält **kein** `.env` / `.env.local` / `secrets/` / `credentials/` → Risiko, dass ein Entwickler ein lokales `.env`-File aus Versehen committet.
3. Kein `.env.example` mit Placeholder-Werten → Onboarding-Hürde, plus keine kanonische Quelle für die erwarteten Env-Var-Namen.
4. Keine `gitleaks`/`trufflehog`-Action in `.github/workflows/` → kein automatisches Secret-Scanning auf Push.

## Expected Behavior

Per Best-Practice-Katalog (`ARCH-005`):

```python
# config.py
from pydantic import SecretStr

class Settings(BaseSettings):
    consumer_key: SecretStr = Field(..., validation_alias="SRGSSR_CONSUMER_KEY")
    consumer_secret: SecretStr = Field(..., validation_alias="SRGSSR_CONSUMER_SECRET")
```

```gitignore
# .gitignore
.env
.env.local
.env.*.local
secrets/
credentials/
```

```yaml
# .github/workflows/secret-scan.yml
- uses: gitleaks/gitleaks-action@v2
```

## Evidence

- `src/srgssr_mcp/config.py:29-30`:
  ```python
  consumer_key: str = Field(default="", validation_alias="SRGSSR_CONSUMER_KEY")
  consumer_secret: str = Field(default="", validation_alias="SRGSSR_CONSUMER_SECRET")
  ```
- `cat .gitignore` zeigt: `.venv/`, `__pycache__/`, `*.pyc` etc. — **kein `.env`**
- `ls -la /home/user/srgssr-mcp/ | grep -E "\.env"` → kein `.env.example`
- `grep -rE "gitleaks|trufflehog" .github/workflows/` → keine Treffer
- `grep -rE "(api[_-]?key|password|secret|token).*=.*['\"][^'\"]{16,}['\"]" src/` → keine Klartext-Secrets (gut)

## Risk Description

- **Konkret:** Wenn ein Entwickler lokal Tests mit echtem `consumer_secret` laufen lässt und `git add .` macht, landet die `.env` im Repo. `gitleaks` würde das fangen — aber ist nicht aktiv.
- **In-Memory-Leak:** Jede `repr(settings)` / `dict(settings)` / `logger.info("loaded", settings=settings)`-Operation würde den Klartext-Secret in Logs schreiben. Mit `SecretStr` wäre das `**********`.
- **Public Repo:** Das Repo ist auf GitHub öffentlich (`malkreide/srgssr-mcp`) — accidentaler Push einer `.env` ist sofort öffentlich; selbst `git rm` reicht nicht (history rewrite nötig).

## Remediation

```diff
# pyproject.toml: bereits pydantic >= 2.0 — keine Dep-Änderung nötig

# src/srgssr_mcp/config.py
- from pydantic import Field
+ from pydantic import Field, SecretStr

  class Settings(BaseSettings):
-     consumer_key: str = Field(default="", validation_alias="SRGSSR_CONSUMER_KEY")
-     consumer_secret: str = Field(default="", validation_alias="SRGSSR_CONSUMER_SECRET")
+     consumer_key: SecretStr = Field(default=SecretStr(""), validation_alias="SRGSSR_CONSUMER_KEY")
+     consumer_secret: SecretStr = Field(default=SecretStr(""), validation_alias="SRGSSR_CONSUMER_SECRET")
```

In `_http.py`, wo das Secret konsumiert wird:

```diff
- credentials = base64.b64encode(f"{consumer_key}:{consumer_secret}".encode()).decode()
+ credentials = base64.b64encode(
+     f"{consumer_key.get_secret_value()}:{consumer_secret.get_secret_value()}".encode()
+ ).decode()
```

```diff
# .gitignore
+ .env
+ .env.local
+ .env.*.local
+ secrets/
+ credentials/
```

```bash
# Neu: .env.example
SRGSSR_CONSUMER_KEY=your-consumer-key-here
SRGSSR_CONSUMER_SECRET=your-consumer-secret-here
SRGSSR_LOG_LEVEL=info
SRGSSR_MCP_TRANSPORT=stdio
```

```yaml
# Neu: .github/workflows/secret-scan.yml
name: Secret Scan
on: [push, pull_request]
jobs:
  gitleaks:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - uses: gitleaks/gitleaks-action@v2
```

## Effort Estimate

**S** — < 1 Tag. Vier kleine Änderungen plus ein neues Workflow-File.

## Dependencies / Blockers

Keine.

## Verification After Fix

- Re-Audit ARCH-005
- `grep -rE 'SecretStr' src/srgssr_mcp/config.py` muss 2 Treffer haben
- `cat .gitignore | grep -E '^\.env'` muss min. 1 Treffer haben
- `ls .env.example` muss existieren
- `ls .github/workflows/secret-scan.yml` muss existieren
- gitleaks-Action muss bei Test-Push einen Klartext-Secret fangen
