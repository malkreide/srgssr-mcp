# Secret Management

This document records the current secret-storage maturity stage of
`srgssr-mcp`, the rationale, and the trigger conditions for an upgrade.
Aligned with the SEC-013 entry of the [`mcp-audit-skill`][skill] catalog.

[skill]: https://github.com/malkreide/mcp-audit-skill

## Current Stage — 1 (Plain Environment Variables)

`SRGSSR_CONSUMER_KEY` and `SRGSSR_CONSUMER_SECRET` are loaded from process
environment variables (or, for local development, from a `.env` file)
via `pydantic-settings.BaseSettings` (see `src/srgssr_mcp/config.py`).
Values are typed as `pydantic.SecretStr` so they are masked in `repr`,
`str`, and accidental structured-log emissions (ARCH-005).

The cached `Settings` instance has a bounded **5-minute TTL** so rotated
upstream credentials take effect without a process restart.

### Why Stage 1 is acceptable here

- `data_class = Public Open Data` (SRG SSR public APIs only)
- `write_capable = false` — all tools are read-only
- Single-tenant — no multi-user server, no per-user credentials
- Single-provider — only `api.srgssr.ch` is reached

Per SEC-013, Stage 1 is explicitly permitted for Public-Open-Data servers
when documented.

## Eskalations-Trigger

Switch to **Stage 3** (managed Secret Manager) before any of the
following becomes true:

| Trigger | Recommended action |
|---|---|
| Cloud deployment (Kubernetes, ECS, Render, Railway) | External Secrets Operator + AWS Secrets Manager (eu-central-1 / Switzerland North) or Azure Key Vault |
| Multi-tenant operation (per-user credentials) | Per-tenant secret namespacing in the chosen Secret Manager |
| Tool set extended with write paths | Stage 3 + write-path approval flow (HITL-005) |
| Compliance scope changes (PII, Verwaltungsdaten) | Stage 3 + ISDS / DSG review |

### Stage-3 reference plan

```
EnvSourceFunc <- ExternalSecretsOperator <- AWS Secrets Manager
                                              ├ srgssr/consumer-key
                                              └ srgssr/consumer-secret
```

The application code does not change between Stage 1 and Stage 3 — both
use environment variables. The difference is who populates the variables
and how rotation is automated. The 5-minute TTL on `get_settings()` then
becomes the rotation latency.

## Local development

1. Copy `.env.example` to `.env`
2. Fill in the credentials from <https://developer.srgssr.ch>
3. `.env` is in `.gitignore` — do not commit it
4. The repository's `.github/workflows/secret-scan.yml` runs `gitleaks` on
   every push to detect accidental secret commits
