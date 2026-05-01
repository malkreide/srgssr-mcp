"""HTTP plumbing: OAuth2 token cache, authenticated GET helpers, error mapper."""

import base64
import ipaddress
import socket
import time
import unicodedata
from urllib.parse import urlparse

import httpx

from srgssr_mcp.config import get_settings
from srgssr_mcp.logging_config import get_logger

logger = get_logger("mcp.srgssr.http")

BASE_URL = "https://api.srgssr.ch"
TOKEN_URL = f"{BASE_URL}/oauth/v1/accesstoken"
WEATHER_BASE = f"{BASE_URL}/forecasts/v2.0/weather"
VIDEO_BASE = f"{BASE_URL}/video/v3"
AUDIO_BASE = f"{BASE_URL}/audio/v3"
EPG_BASE = f"{BASE_URL}/epg/v3"
POLIS_BASE = f"{BASE_URL}/polis/v1"

TIMEOUT = 30.0
USER_AGENT = "srgssr-mcp/1.0.0 (github.com/malkreide/srgssr-mcp)"

# SSRF defense (SEC-004 + SEC-021): every outbound HTTP request is restricted
# to the SRG SSR API host, must use HTTPS, and the resolved IPs must not fall
# in any private, loopback, link-local, multicast, or otherwise non-routable
# range. The host allowlist is the primary control; the IP blocklist is
# defense-in-depth against DNS rebinding, a compromised resolver, or future
# code that constructs URLs from less-trusted input.
ALLOWED_HOSTS: frozenset[str] = frozenset({"api.srgssr.ch"})

_BLOCKED_IP_NETWORKS: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...] = (
    ipaddress.ip_network("0.0.0.0/8"),       # "this network"
    ipaddress.ip_network("10.0.0.0/8"),      # RFC1918 private
    ipaddress.ip_network("100.64.0.0/10"),   # CGNAT
    ipaddress.ip_network("127.0.0.0/8"),     # loopback
    ipaddress.ip_network("169.254.0.0/16"),  # link-local (cloud metadata)
    ipaddress.ip_network("172.16.0.0/12"),   # RFC1918 private
    ipaddress.ip_network("192.0.0.0/24"),    # IETF protocol assignments
    ipaddress.ip_network("192.168.0.0/16"),  # RFC1918 private
    ipaddress.ip_network("198.18.0.0/15"),   # benchmarking
    ipaddress.ip_network("224.0.0.0/4"),     # multicast
    ipaddress.ip_network("240.0.0.0/4"),     # reserved (incl. broadcast)
    ipaddress.ip_network("::1/128"),         # IPv6 loopback
    ipaddress.ip_network("::/128"),          # IPv6 unspecified
    ipaddress.ip_network("::ffff:0:0/96"),   # IPv4-mapped IPv6
    ipaddress.ip_network("64:ff9b::/96"),    # IPv4/IPv6 translation
    ipaddress.ip_network("fc00::/7"),        # IPv6 unique-local
    ipaddress.ip_network("fe80::/10"),       # IPv6 link-local
    ipaddress.ip_network("ff00::/8"),        # IPv6 multicast
)

_token_cache: dict = {"access_token": None, "expires_at": 0.0}


def _validate_url_safe(url: str) -> None:
    """Reject ``url`` if it would expose the server to SSRF.

    Three controls are enforced before any outbound request is issued:

    1. **HTTPS-only** — ``http://``, ``file://`` and other schemes are refused.
    2. **Egress allowlist** — the hostname must appear in :data:`ALLOWED_HOSTS`.
    3. **IP blocklist** — every address the hostname resolves to is checked
       against :data:`_BLOCKED_IP_NETWORKS`; resolution to any private,
       loopback, link-local, multicast or reserved range aborts the request.

    Raises :class:`ValueError` on any violation. The caller (``_api_get`` /
    ``_get_access_token``) propagates the exception, which is mapped to a
    localized "Konfigurationsfehler" by :func:`_handle_error` so internal
    network details are not leaked to the MCP client.
    """
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError(
            f"SSRF blocked: only HTTPS is permitted for outbound requests "
            f"(got scheme '{parsed.scheme}')"
        )
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("SSRF blocked: URL has no hostname")
    if hostname not in ALLOWED_HOSTS:
        raise ValueError(
            f"SSRF blocked: host '{hostname}' is not in the egress allowlist "
            f"({sorted(ALLOWED_HOSTS)})"
        )
    try:
        addr_infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as e:
        raise ValueError(
            f"SSRF blocked: cannot resolve host '{hostname}' ({e})"
        ) from e
    for info in addr_infos:
        ip = ipaddress.ip_address(info[4][0])
        for blocked in _BLOCKED_IP_NETWORKS:
            if ip.version == blocked.version and ip in blocked:
                raise ValueError(
                    f"SSRF blocked: host '{hostname}' resolves to {ip} "
                    f"which is in blocked range {blocked}"
                )


def _get_credentials() -> tuple[str, str]:
    return get_settings().require_credentials()


async def _get_access_token() -> str:
    """Returns a valid OAuth2 access token, refreshing if necessary."""
    now = time.time()
    if _token_cache["access_token"] and _token_cache["expires_at"] > now + 60:
        logger.debug("oauth_token_cache_hit")
        return _token_cache["access_token"]

    key, secret = _get_credentials()
    credentials = base64.b64encode(f"{key}:{secret}".encode()).decode()

    _validate_url_safe(TOKEN_URL)
    logger.info("oauth_token_refresh")
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(
            TOKEN_URL,
            params={"grant_type": "client_credentials"},
            headers={
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": USER_AGENT,
            },
        )
        resp.raise_for_status()
        data = resp.json()

    _token_cache["access_token"] = data["access_token"]
    expires_in = int(data.get("expires_in", 3600))
    _token_cache["expires_at"] = now + expires_in
    logger.info("oauth_token_acquired", expires_in=expires_in)
    return _token_cache["access_token"]


async def _api_get(url: str, params: dict | None = None) -> dict:
    """Authenticated GET helper returning parsed JSON."""
    _validate_url_safe(url)
    token = await _get_access_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    }
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(url, params=params, headers=headers)
        resp.raise_for_status()
        return resp.json()


async def _safe_api_get(
    url: str, params: dict | None = None, not_found_hint: str | None = None
) -> dict | str:
    """Like :func:`_api_get` but returns a localized error string on failure.

    Used by aggregation tools that fan out via :func:`asyncio.gather` and want
    to render partial results when one upstream endpoint is unavailable.
    """
    try:
        return await _api_get(url, params=params)
    except Exception as e:
        return _handle_error(e, not_found_hint=not_found_hint)


def _handle_error(e: Exception, not_found_hint: str | None = None) -> str:
    if isinstance(e, ValueError):
        return f"Konfigurationsfehler: {e}"
    if isinstance(e, httpx.HTTPStatusError):
        sc = e.response.status_code
        if sc == 401:
            return "Fehler 401: Ungültige API-Credentials. Bitte SRGSSR_CONSUMER_KEY und SRGSSR_CONSUMER_SECRET prüfen."
        if sc == 403:
            return (
                "Fehler 403: Zugriff verweigert. Möglicherweise fehlt der Zugriff"
                " auf diese API im gewählten Produkt."
            )
        if sc == 404:
            base = "Fehler 404: Ressource nicht gefunden. Bitte ID oder Parameter prüfen."
            return f"{base}\n\n**Tipp:** {not_found_hint}" if not_found_hint else base
        if sc == 429:
            return "Fehler 429: Rate-Limit überschritten. Bitte etwas warten und erneut versuchen."
        return f"API-Fehler {sc}: {e.response.text[:200]}"
    if isinstance(e, httpx.TimeoutException):
        return "Fehler: Anfrage hat das Timeout überschritten. Bitte erneut versuchen."
    return f"Unerwarteter Fehler ({type(e).__name__}): {e}"


def _query_variants(query: str) -> list[str]:
    """Returns deduplicated query variants for fuzzy retry.

    Generates the original query plus normalized forms (ASCII-folded for
    diacritic-insensitive matching, lowercased, title-cased) so that a search
    for "Zurich" still hits "Zürich" upstream and vice versa.
    """
    seen: set[str] = set()
    variants: list[str] = []
    folded = "".join(
        c for c in unicodedata.normalize("NFKD", query) if not unicodedata.combining(c)
    )
    for v in (query, folded, query.lower(), folded.lower(), query.title(), folded.title()):
        v = v.strip()
        if v and v not in seen:
            seen.add(v)
            variants.append(v)
    return variants
