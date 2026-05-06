# Finding: SEC-005 — DNS-Rebinding-Prevention: DNS-Pinning gegen TOCTOU

| Feld | Wert |
|---|---|
| **Severity** | high |
| **Status** | open |
| **Server** | `srgssr-mcp` |
| **Check-Reference** | `SEC-005` |
| **Audit-Datum** | 2026-05-06 |
| **Auditor** | Claude (mcp-audit-skill v0.5.0) |

## Observed Behavior

`_validate_url_safe()` in `src/srgssr_mcp/_http.py` macht eine DNS-Resolution für die IP-Allowlist-Prüfung, gibt dann aber die Original-URL (mit Hostname) an httpx weiter. httpx löst den Hostname intern ein zweites Mal auf — klassisches TOCTOU-Fenster für DNS-Rebinding.

```python
# Vereinfacht aus _http.py:
def _validate_url_safe(url: str) -> None:
    ...
    addr_infos = socket.getaddrinfo(hostname, None)  # 1. Resolution für Range-Check
    for info in addr_infos:
        if _is_private_ip(info[4][0]):
            raise ValueError("blocked")

# Aufruf:
_validate_url_safe(TOKEN_URL)
async with httpx.AsyncClient(...) as client:
    response = await client.get(TOKEN_URL)  # 2. Resolution, möglicherweise andere IP
```

Kein DNS-Pinning, kein Custom-Transport mit gepinnter IP, keine `Host`-Header-Manipulation für SNI.

## Expected Behavior

Per Best-Practice-Katalog (`SEC-005`): Nur **eine** DNS-Resolution; der gefundene IP wird als Connect-Target genutzt, der Hostname nur für SNI/Host-Header:

```python
import httpx, socket

class PinnedTransport(httpx.AsyncHTTPTransport):
    def __init__(self, hostname: str, **kwargs):
        addr = socket.getaddrinfo(hostname, None)[0][4][0]
        # ... Validation der IP
        self._pinned_url = lambda url: url.copy_with(host=addr)
        super().__init__(**kwargs)

# Oder: Egress-Proxy (Stripe Smokescreen) via HTTPS_PROXY-Env-Var.
```

## Evidence

- `src/srgssr_mcp/_http.py`: `socket.getaddrinfo(hostname, None)` — nur einmal, dann Original-URL an httpx
- `grep -rE 'replace\(.*hostname.*resolved|Host:.*hostname|pinned_url' src/` → keine Treffer
- `grep -rE 'sni_hostname|SSLContext' src/` → keine Treffer
- `ALLOWED_HOSTS = frozenset({"api.srgssr.ch"})` (`_http.py:34`) — Mitigant: nur 1 Domain im Scope

## Risk Description

- **Theoretisches Worst-Case:** Angreifer kontrolliert DNS für `api.srgssr.ch` → Validation sieht öffentliche IP, httpx bekommt private/loopback-IP → SSRF in interne Netze.
- **Realistisches Risiko:** Niedrig, weil:
  - SRG SSR kontrolliert die Domain
  - Single-Host-Allowlist (kein User-supplied URL)
  - Read-only-Server, keine Write-Pfade
- **Defense-in-Depth-Lücke:** Der Check verlangt explizit DNS-Pinning oder Egress-Proxy als Layer-2 — bei Cloud-Deployment mit erweitertem Scope (mehrere Domains, weniger Trust) wird das Pflicht.

## Remediation

**Option A (Code-Layer-Fix):**

```diff
+ class PinnedTransport(httpx.AsyncHTTPTransport):
+     async def handle_async_request(self, request):
+         resolved_ip = socket.getaddrinfo(request.url.host, None)[0][4][0]
+         _validate_ip_allowed(resolved_ip)
+         # Replace host in URL with IP, keep Host header for SNI
+         new_url = request.url.copy_with(host=resolved_ip)
+         new_request = request.copy_with(url=new_url, headers={**request.headers, "Host": request.url.host})
+         return await super().handle_async_request(new_request)
+
+ transport = PinnedTransport()
- async with httpx.AsyncClient(timeout=TIMEOUT) as client:
+ async with httpx.AsyncClient(timeout=TIMEOUT, transport=transport) as client:
```

**Option B (Network-Layer-Fix):** Egress-Proxy einsetzen — z.B. `stripe/smokescreen` mit Allowlist `api.srgssr.ch`. Setzt `HTTPS_PROXY=http://smokescreen:4750` als Env-Var. Smokescreen macht DNS-Pinning automatisch.

Option B ist robuster (sprachunabhängig, zentralisierbar, auditierbar) und wird in `docs/network-egress.md` bereits als Defense-in-Depth-Plan erwähnt.

## Effort Estimate

**M** — 1–3 Tage für Option A inkl. Tests gegen Mock-Resolver. Option B ist deployment-spezifisch (Container-Sidecar).

## Dependencies / Blockers

Keine. Kann unabhängig von SDK-001 / SEC-021 implementiert werden.

## Verification After Fix

- Re-Audit SEC-005
- Test mit Mock-Resolver, der zwei verschiedene IPs returnt — der zweite Lookup darf das Ergebnis nicht ändern
- `grep -rE 'PinnedTransport|sni_hostname' src/` muss min. 1 Treffer liefern (Option A) oder Doc-Update zum Egress-Proxy (Option B)
