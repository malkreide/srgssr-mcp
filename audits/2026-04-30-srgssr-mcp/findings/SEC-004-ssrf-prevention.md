# Finding: SEC-004 — SSRF-Prevention: HTTPS-Enforcement + IP-Blocklisting

| Feld | Wert |
|---|---|
| **Severity** | high |
| **Status** | resolved |
| **Server** | `srgssr-mcp` |
| **Check-Reference** | `SEC-004` |
| **PDF-Reference** | Anhang B4 |
| **Audit-Datum** | 2026-04-30 |
| **Auditor** | Claude (mcp-audit-skill v0.5.0) |

## Observed Behavior

- Server nutzt `httpx.AsyncClient` für externe Requests
- Automated Check konnte **keine** HTTPS-Enforcement oder IP-Blocklisting verifizieren
- Manuelle Code-Review erforderlich

## Expected Behavior

```python
import ipaddress
from urllib.parse import urlparse

BLOCKED_IP_RANGES = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),  # Link-local
    ipaddress.ip_network("127.0.0.0/8"),     # Loopback
]

def validate_url_safe(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError(f"Only HTTPS allowed, got: {parsed.scheme}")

    # Resolve hostname to IP, check against blocklist
    ip = ipaddress.ip_address(socket.gethostbyname(parsed.hostname))
    for blocked in BLOCKED_IP_RANGES:
        if ip in blocked:
            raise ValueError(f"IP {ip} in blocked range {blocked}")
```

## Remediation

Implementiert in `src/srgssr_mcp/_http.py` (`_validate_url_safe`,
`ALLOWED_HOSTS`, `_BLOCKED_IP_NETWORKS`) — kombiniert SEC-004 (HTTPS +
IP-Blocklist) mit SEC-021 (Egress-Allowlist) in einer einzigen Prüfung, die
vor jedem Aufruf von `httpx` läuft.

**Drei Kontrollen pro Request:**

1. **HTTPS-Enforcement** — `urlparse(url).scheme != "https"` lehnt sofort ab
   (`http://`, `file://`, `ftp://`, `gopher://` …).
2. **Egress-Allowlist (SEC-021)** — `parsed.hostname` muss in
   `ALLOWED_HOSTS = {"api.srgssr.ch"}` liegen. Subdomain-Tricks wie
   `api.srgssr.ch.evil.example` werden hier abgefangen.
3. **IP-Blocklist (Defense-in-Depth)** — `socket.getaddrinfo(hostname, None)`
   liefert *alle* A/AAAA-Records; jede aufgelöste IP wird gegen folgende
   Ranges geprüft, jede einzelne Treffer-IP führt zur Ablehnung:

   | Range | Zweck |
   |---|---|
   | `0.0.0.0/8` | "this network" |
   | `10.0.0.0/8` | RFC1918 privat |
   | `100.64.0.0/10` | CGNAT |
   | `127.0.0.0/8` | Loopback |
   | `169.254.0.0/16` | Link-Local (inkl. `169.254.169.254` Cloud-Metadata) |
   | `172.16.0.0/12` | RFC1918 privat |
   | `192.0.0.0/24` | IETF-Protokoll-Zuweisungen |
   | `192.168.0.0/16` | RFC1918 privat |
   | `198.18.0.0/15` | Benchmarking |
   | `224.0.0.0/4` | Multicast |
   | `240.0.0.0/4` | Reserved (inkl. Broadcast) |
   | `::1/128` | IPv6 Loopback |
   | `::/128` | IPv6 unspecified |
   | `::ffff:0:0/96` | IPv4-mapped IPv6 |
   | `64:ff9b::/96` | IPv4/IPv6-Translation |
   | `fc00::/7` | IPv6 Unique-Local (ULA) |
   | `fe80::/10` | IPv6 Link-Local |
   | `ff00::/8` | IPv6 Multicast |

**Aufrufstellen:**

- `_get_access_token()` validiert `TOKEN_URL` vor dem OAuth-POST.
- `_api_get(url)` validiert die übergebene URL vor jedem GET.
- `_safe_api_get` ruft `_api_get` und mappt den `ValueError` über
  `_handle_error` auf eine lokalisierte `Konfigurationsfehler: …`-Meldung —
  interne Netz-Details werden nicht an den MCP-Client geleakt.

**Gegen DNS-Rebinding** wird *jede* aufgelöste IP geprüft (nicht nur die
erste): wenn ein kompromittierter Resolver zwei A-Records liefert (eine
öffentliche und eine private), schlägt die Validierung fehl.

## Effort Estimate

**M** — 1-3 Tage (kombiniert mit SEC-021).

## Verification After Fix

Status: **resolved** — Akzeptanzkriterien erfüllt.

```bash
# Lint sauber
$ ruff check src/
All checks passed!

# Test-Coverage 100% auf _http.py
$ pytest --cov=src/srgssr_mcp --cov-report=term-missing
src/srgssr_mcp/_http.py     101      0   100%
TOTAL                       771     26    97%

# 20 neue SSRF-Tests
$ pytest -k "ssrf or validate_url or api_get_blocks or all_base_urls or token_url_is_https or maps_ssrf"
20 passed in 0.13s

# Komplette Suite weiter grün
$ pytest
114 passed, 14 skipped in 2.37s
```

**Test-Abdeckung:**

- HTTPS-Enforcement: `http://`, `file://`, `ftp://`, leerer Hostname.
- Allowlist: fremder Host, Subdomain-Suffix-Trick.
- IP-Blocklist: RFC1918, Loopback, Link-Local (AWS-Metadata `169.254.169.254`),
  IPv6 Loopback, IPv6 ULA, gemischte A/AAAA-Antwort mit *einer* privaten IP.
- DNS-Resolver-Fehler.
- Integration: `_api_get` blockt non-HTTPS und nicht-allowlisted Hosts;
  `_safe_api_get` liefert lokalisierte Konfigurationsfehler-Meldung.
- Konsistenz: alle hard-coded Base-URLs (`BASE_URL`, `WEATHER_BASE`,
  `VIDEO_BASE`, `AUDIO_BASE`, `EPG_BASE`, `POLIS_BASE`, `TOKEN_URL`)
  erfüllen die SSRF-Policy.
