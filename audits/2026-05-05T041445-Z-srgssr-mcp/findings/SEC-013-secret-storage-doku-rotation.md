# Finding: SEC-013 — API-Key-Storage: Secret Manager statt Plain-Text Env-Vars

| Feld | Wert |
|---|---|
| **Severity** | high |
| **Status** | open |
| **Server** | `srgssr-mcp` |
| **Check-Reference** | `SEC-013` |
| **Audit-Datum** | 2026-05-06 |
| **Auditor** | Claude (mcp-audit-skill v0.5.0) |

## Observed Behavior

Secret-Storage-Reife: **Stufe 1** (Plain Env-Var via `pydantic-settings.BaseSettings`). `SRGSSR_CONSUMER_KEY` / `SRGSSR_CONSUMER_SECRET` werden aus Environment oder `.env`-File geladen (`src/srgssr_mcp/config.py:29-30`).

Profil sagt `data_class=Public Open Data` → laut Check ist Stufe 1 dafür akzeptabel — **wenn dokumentiert**.

Lücken:

1. Keine `docs/secret-management.md` mit Stufe-1-Akzeptanz-Begründung
2. `lru_cache(maxsize=1)` auf `get_settings()` → Secret-Rotation erfordert Process-Restart, kein TTL-Cache
3. Bei zukünftigem K8s-Deployment (siehe `docs/network-egress.md`) ist Stufe 3 (Secret Manager) zu erwägen — aktuell keine `boto3` / `azure-keyvault` / `google-cloud-secret-manager`-Dep
4. Synergetisch mit ARCH-005: `consumer_secret: str` (nicht `SecretStr`) → In-Memory-Klartext

## Expected Behavior

Per Best-Practice-Katalog (`SEC-013`): Stufen-Eskalation mit dokumentierter Begründung.

```markdown
# docs/secret-management.md

## Aktuelle Stufe: 1 (Plain Env-Var)

Begründung: `data_class=Public Open Data`, kein PII-Bezug, keine destruktiven
Operationen (`write_capable=false`). Stufe 1 ist gemäss SEC-013-Pass-Pattern
akzeptabel.

## Eskalations-Trigger

Bei einem der folgenden Trigger ist auf Stufe 3 (Secret Manager) zu wechseln:
- Cloud-Deployment (K8s, ECS, Render)
- Multi-Tenant-Betrieb
- Tool-Set erweitert um Write-Pfade
```

Plus TTL-Cache:

```python
from cachetools import TTLCache, cached

@cached(cache=TTLCache(maxsize=1, ttl=300))
def get_settings() -> Settings:
    return Settings()
```

## Evidence

- `src/srgssr_mcp/config.py:51`: `@lru_cache(maxsize=1)` → keine Rotation ohne Restart
- `grep -rE 'boto3|secretsmanager|hvac|azure-keyvault|google-cloud-secret-manager' pyproject.toml` → keine Treffer
- `ls docs/` → nur `network-egress.md`, keine `secret-management.md`

## Risk Description

- **Aktuell akzeptabel:** Public Open Data, Stufe 1 ist im Check explizit erlaubt.
- **Operationelles Risiko (Rotation):** Falls SRG SSR die Credentials rotieren würde (oder sie ein Leak hätten), müsste der Server-Prozess neu gestartet werden, weil `lru_cache` für die Lifetime persistiert. Bei Cloud-Deployment mit langlebigen Pods ist das ein Problem.
- **Skalierungsrisiko:** Bei zukünftigem K8s-Rollout (siehe `docs/network-egress.md`) ist Stufe 1 nicht mehr ausreichend — External Secrets Operator + AWS Secrets Manager (eu-central-1 oder Azure Key Vault Switzerland North) wäre der Standard.

## Remediation

Phase 1 (S, sofort): Doku-Stub erstellen.

```diff
+ # docs/secret-management.md (neu)
+
+ # Secret Management
+
+ ## Aktuelle Stufe
+
+ Stufe 1 (Plain Env-Var via pydantic-settings).
+
+ ## Akzeptanz-Begründung
+
+ - `data_class=Public Open Data` (SRG SSR Public API)
+ - `write_capable=false`
+ - Single-Tenant (kein Multi-User-Server)
+
+ ## Eskalation auf Stufe 3 (Secret Manager) bei:
+ - Cloud-Deployment (K8s/ECS/Render)
+ - Multi-Tenant-Betrieb
+ - Tool-Set erweitert um Write-Pfade
```

Phase 2 (S): TTL-Cache mit Refresh ohne Restart.

```diff
# pyproject.toml
+ "cachetools>=5.0.0",

# src/srgssr_mcp/config.py
- from functools import lru_cache
+ from cachetools import TTLCache, cached
- @lru_cache(maxsize=1)
+ @cached(cache=TTLCache(maxsize=1, ttl=300))  # Re-read every 5 min
  def get_settings() -> Settings:
      return Settings()
```

Phase 3 (M, bei Cloud-Migration): External Secrets Operator + AWS/Azure Secret Manager. Plan in `docs/secret-management.md` skizzieren.

## Effort Estimate

**S** für Phase 1 + 2. **M** für Phase 3 (deployment-spezifisch).

## Dependencies / Blockers

Synergetisch mit ARCH-005 (Secret-Hygiene) — gleiche Files betroffen.

## Verification After Fix

- Re-Audit SEC-013
- `ls docs/secret-management.md` muss existieren
- `grep -rE 'TTLCache|cachetools' src/srgssr_mcp/config.py` muss min. 1 Treffer haben
- (Phase 3) Wenn cloud-deployed: External Secrets Manager dokumentiert
