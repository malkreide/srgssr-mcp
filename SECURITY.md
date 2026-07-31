# 🛡️ Security Policy & Posture

[🇩🇪 Deutsche Version](SECURITY.de.md)

`srgssr-mcp` is part of the [Swiss Public Data MCP Portfolio](https://github.com/malkreide)
and was hardened against the internal MCP best-practice audit catalogue. This
document summarises the security posture and records the **accepted-risk**
decisions for controls that are deliberately handled at the portfolio/gateway
layer rather than inside this single server.

## Supported Versions

| Version | Supported |
|---|---|
| `0.1.x` | ✅ |

Security fixes are released against the latest `0.1.x` line. Older pre-release
builds are not maintained.

## Reporting a Vulnerability

Please open a private [security advisory](https://github.com/malkreide/srgssr-mcp/security/advisories/new)
on the GitHub repository, or contact the maintainer listed in [`README.md`](README.md).
**Do not file public issues for exploitable vulnerabilities.**

When reporting, please include:

- A description of the vulnerability and its impact
- Steps to reproduce (proof-of-concept if possible)
- Affected version / commit
- Any suggested remediation

You can expect an initial acknowledgement within a few days. Confirmed issues
are tracked in [`CHANGELOG.md`](CHANGELOG.md) once a fix ships.

## Posture Summary

This is a **read-only**, **no-PII** MCP server. All tools only issue
`GET`-style requests (via OAuth2 Client Credentials) against a single fixed
upstream host — the **SRG SSR Public API V2** (`api.srgssr.ch`). Hardening
already in place:

| Area | Control |
|---|---|
| Egress | HTTPS-only code-layer allowlist to `api.srgssr.ch`; no user-controlled URLs are constructed (SEC-004 / SEC-021) — see [Egress Allowlist](README.md#egress-allowlist) |
| SSRF / DNS rebinding | Every resolved IP is checked against private, loopback, link-local (incl. `169.254.169.254`), CGNAT, multicast and reserved ranges; a single shared TTL-cached DNS resolution closes the TOCTOU window (SEC-005) |
| TLS | Certificate verification on by default (httpx default); never disabled |
| Binding | stdio transport by default; the optional HTTP/SSE transport binds via the SDK default and is driven by explicit env vars (`SRGSSR_MCP_HOST`/`PORT`) |
| Input | Pydantic v2 strict validation on every tool input model; business units and IDs validated before any request is issued |
| Tools | Every tool sets `readOnlyHint: True`; no write, mutate or delete paths exist by design (Phase 1: Read-only Wrapper) |
| Secrets | `SRGSSR_CONSUMER_KEY` / `SRGSSR_CONSUMER_SECRET` are typed as `pydantic.SecretStr` — never rendered in `repr()` or logs (ARCH-005); `.env*` and `secrets/` are git-ignored; a `gitleaks` secret-scan workflow runs on every push |
| Secret management | Stage-1 (plain env var) storage with a documented acceptance rationale and escalation triggers — see [`docs/secret-management.md`](docs/secret-management.md) (SEC-013) |
| Errors | Upstream error bodies and stack traces are logged to stderr only; the model receives a generic, non-leaking message (OBS-002) |
| Stdout | Reserved for the JSON-RPC stream; all structured logging pinned to stderr (OBS-003) |
| Resilience | A 30s per-request timeout bounds every upstream call |

See [`CHANGELOG.md`](CHANGELOG.md) for the hardening history and the
[`audits/`](audits/) directory for the underlying audit reports and findings.

## Accepted Risks (portfolio-level controls)

The following audit checks are **not** implemented inside this server by design.
They are portfolio-wide concerns best enforced at an MCP gateway / host layer,
and the residual risk here is low because the server is read-only and only
reaches a single trusted public-data provider.

### SEC-014 — Tool allow-listing via an MCP gateway

**Status:** accepted risk (portfolio-level).
A per-tool allow-list belongs to the MCP host/gateway that aggregates multiple
servers, not to an individual server that exposes a fixed, read-only tool set.
If/when a central gateway is introduced for the portfolio, tool allow-listing
should be configured there. Until then, the risk is bounded: every tool is
read-only and constrained to the fixed endpoint above.

### SEC-015 — Pre-flight tool-poisoning detection

**Status:** accepted risk (portfolio-level) — with a local guard in place.
Tool-poisoning (malicious tool descriptions / rug-pulls) is a supply-chain and
host-side concern. This server's tool definitions are version-controlled,
authored in-repo, and reviewed via PR; there is no dynamic or remote tool
registration. Cross-server poisoning detection remains a gateway/host
responsibility tracked at the portfolio level.

## Re-evaluation Triggers

These acceptances should be revisited if the server ever:

- gains **write** capability or starts processing **PII**, or
- adds an **authentication** model for end users (then implement bound, TTL'd,
  server-side-invalidated session IDs and re-audit before merge), or
- is deployed to the **cloud** as a long-lived HTTP/SSE service (then escalate
  secret storage to a managed Secret Manager per [`docs/secret-management.md`](docs/secret-management.md)
  and apply the network-layer egress controls in [`docs/network-egress.md`](docs/network-egress.md)), or
- registers tools **dynamically** / from remote sources, or
- is aggregated behind a shared MCP gateway (then enable the gateway's tool
  allow-listing and tool-poisoning detection).
