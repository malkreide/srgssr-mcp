"""HTTP plumbing: OAuth2 token cache, authenticated GET helpers, error mapper."""

import asyncio
import base64
import ipaddress
import random
import socket
import time
import unicodedata
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

import httpx

from srgssr_mcp import __version__
from srgssr_mcp.config import get_settings
from srgssr_mcp.logging_config import get_logger

logger = get_logger("mcp.srgssr.http")

BASE_URL = "https://api.srgssr.ch"
TOKEN_URL = f"{BASE_URL}/oauth/v1/accesstoken"
WEATHER_BASE = f"{BASE_URL}/srf-meteo/v2"
VIDEO_BASE = f"{BASE_URL}/videometadata/v2"
AUDIO_BASE = f"{BASE_URL}/audiometadata/v2"
EPG_BASE = f"{BASE_URL}/epg/v3"
POLIS_BASE = f"{BASE_URL}/polis-api/v2"

TIMEOUT = 30.0
# Derived from the package version, not hand-maintained: this literal read
# "srgssr-mcp/1.0.0" while the package was at 1.0.3.
USER_AGENT = f"srgssr-mcp/{__version__} (github.com/malkreide/srgssr-mcp)"

# --- Retry policy toward the SRG SSR API gateway (ARCH-014) ------------------
# Three questions a retry has to answer: *what* is retried, *how fast*, and
# *how long*. The first is settled in _request_with_retry (4xx except 429 fails
# fast); these constants settle the other two.

RETRY_ATTEMPTS = 4

# Ceiling on the *whole* call — the token refresh, the request it authorises,
# and every wait between them.
#
# An attempt count is not a bound: four attempts at a 30s timeout plus backoff
# run past two minutes, and the number never says so. Worse, the relevant limit
# is not ours. The caller has its own timeout, and past it nobody is listening
# any more — the work continues, the load lands on the gateway, and the result
# goes nowhere.
#
# The anchor is measured, not guessed: the Python MCP SDK ships
# MCP_DEFAULT_TIMEOUT = 30.0 (mcp/shared/_httpx_utils.py). 25s leaves headroom
# for MCP framing and the tool layer above the fetch.
#
# One budget spans the token refresh *and* the request, which is why the
# deadline is threaded through instead of being started twice: giving each its
# own would let a cold cache spend 25s on the token and 25s on the call — 50s
# against a 30s client default, with each half looking innocent on its own.
RETRY_TOTAL_BUDGET = 25.0

# Ceiling for a single wait. Guards two things at once: an exponential ladder
# that would otherwise grow without bound, and a Retry-After the gateway is
# entitled to send but we are not obliged to sit through.
RETRY_MAX_DELAY = 20.0

RETRY_BACKOFF_BASE = 2.0

# Jitter spread. Without it every client that hit the same outage retries in
# lockstep and the load returns as a wave exactly when the gateway recovers —
# the retry storm extends the outage it was meant to bridge. This server does
# not even need several clients to produce that lockstep: the aggregation tools
# fan out via asyncio.gather, so one process manages it alone.
RETRY_JITTER_SPREAD = 0.5  # exponential delays land in [0.5x, 1.5x]

# Applied on top of a Retry-After value, deliberately one-sided: the gateway
# told us when to come back, so later is polite and earlier would be ignoring
# the very header we just read.
RETRY_AFTER_JITTER = 0.25  # lands in [1.0x, 1.25x]

# Statuses that carry a meaningful Retry-After (RFC 9110 §10.2.3). A 429 or 503
# is the gateway answering the exact question the backoff curve is guessing at.
RETRY_AFTER_STATUSES = frozenset({429, 503})

# Backoff sleeps go through this alias so a test can skip them by patching this
# module attribute. Patching ``asyncio.sleep`` itself would reach every module
# in the process: ``test_daily_briefing_runs_upstreams_in_parallel`` uses
# ``asyncio.sleep(0)`` to yield to the event loop, and a no-op'd sleep silently
# serialises the fan-out it is checking for — the test still runs, it just
# stops testing anything.
_sleep = asyncio.sleep

# SSRF defense (SEC-004 + SEC-021): every outbound HTTP request is restricted
# to the SRG SSR API host, must use HTTPS, and the resolved IPs must not fall
# in any private, loopback, link-local, multicast, or otherwise non-routable
# range. The host allowlist is the primary control; the IP blocklist is
# defense-in-depth against DNS rebinding, a compromised resolver, or future
# code that constructs URLs from less-trusted input.
ALLOWED_HOSTS: frozenset[str] = frozenset({"api.srgssr.ch"})

_BLOCKED_IP_NETWORKS: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...] = (
    ipaddress.ip_network("0.0.0.0/8"),  # "this network"
    ipaddress.ip_network("10.0.0.0/8"),  # RFC1918 private
    ipaddress.ip_network("100.64.0.0/10"),  # CGNAT
    ipaddress.ip_network("127.0.0.0/8"),  # loopback
    ipaddress.ip_network("169.254.0.0/16"),  # link-local (cloud metadata)
    ipaddress.ip_network("172.16.0.0/12"),  # RFC1918 private
    ipaddress.ip_network("192.0.0.0/24"),  # IETF protocol assignments
    ipaddress.ip_network("192.168.0.0/16"),  # RFC1918 private
    ipaddress.ip_network("198.18.0.0/15"),  # benchmarking
    ipaddress.ip_network("224.0.0.0/4"),  # multicast
    ipaddress.ip_network("240.0.0.0/4"),  # reserved (incl. broadcast)
    ipaddress.ip_network("::1/128"),  # IPv6 loopback
    ipaddress.ip_network("::/128"),  # IPv6 unspecified
    ipaddress.ip_network("::ffff:0:0/96"),  # IPv4-mapped IPv6
    ipaddress.ip_network("64:ff9b::/96"),  # IPv4/IPv6 translation
    ipaddress.ip_network("fc00::/7"),  # IPv6 unique-local
    ipaddress.ip_network("fe80::/10"),  # IPv6 link-local
    ipaddress.ip_network("ff00::/8"),  # IPv6 multicast
)

_token_cache: dict = {"access_token": None, "expires_at": 0.0}
_token_lock: asyncio.Lock | None = None

# SDK-001: a single shared httpx.AsyncClient is created on first use and held
# for the process lifetime, then closed by the MCPServer lifespan in _app.py.
# This enables HTTP connection pooling across tool calls (no TCP/TLS handshake
# per request), which matters for the aggregation tool that fans out via
# asyncio.gather and for rapid-fire follow-up calls during interactive use.
_http_client: httpx.AsyncClient | None = None
_http_lock: asyncio.Lock | None = None

# SEC-005: process-wide TTL'd DNS cache used by both _validate_url_safe (for
# early IP-allowlist enforcement) and PinnedDNSTransport (for connect-time
# pinning). A single source of truth eliminates the TOCTOU window where the
# pre-flight validation and the actual TCP connect could see different IPs
# (DNS rebinding). Five-minute TTL matches the SETTINGS_TTL_SECONDS rhythm.
DNS_PIN_TTL_SECONDS = 300.0
_dns_pin_cache: dict[str, dict] = {}
_dns_pin_lock: asyncio.Lock | None = None


def _get_lock(slot: str) -> asyncio.Lock:
    """Lazy per-event-loop lock initialiser.

    Locks must be created inside a running event loop because they bind to
    the loop at construction time. Module-level locks would attach to whichever
    loop happens to be running at import time (usually none) and break under
    pytest-asyncio which creates a fresh loop per test.
    """
    global _token_lock, _http_lock, _dns_pin_lock
    if slot == "token":
        if _token_lock is None:
            _token_lock = asyncio.Lock()
        return _token_lock
    if slot == "dns":
        if _dns_pin_lock is None:
            _dns_pin_lock = asyncio.Lock()
        return _dns_pin_lock
    if _http_lock is None:
        _http_lock = asyncio.Lock()
    return _http_lock


def _resolve_and_validate_addrinfo(hostname: str) -> str:
    """Resolve ``hostname`` once and return the first non-blocked IP.

    Synchronous because :func:`socket.getaddrinfo` is synchronous; the caller
    is expected to either run inside an async context (and accept the brief
    blocking call) or wrap it in :func:`asyncio.to_thread`. The blocking time
    is dominated by the OS DNS resolver, which is typically <1 ms on a warm
    cache.

    Raises :class:`ValueError` if any resolved IP is in the SSRF blocklist;
    this preserves the defense against split-horizon DNS where an attacker
    might return a mix of public and private addresses.
    """
    try:
        addr_infos = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise ValueError(f"SSRF blocked: cannot resolve host '{hostname}' ({e})") from e
    if not addr_infos:
        raise ValueError(f"SSRF blocked: no addresses returned for '{hostname}'")

    first_ip: str | None = None
    for info in addr_infos:
        ip_str = info[4][0]
        ip = ipaddress.ip_address(ip_str)
        for blocked in _BLOCKED_IP_NETWORKS:
            if ip.version == blocked.version and ip in blocked:
                raise ValueError(
                    f"SSRF blocked: host '{hostname}' resolves to {ip} which is in blocked range {blocked}"
                )
        if first_ip is None:
            first_ip = ip_str
    assert first_ip is not None
    return first_ip


async def _resolve_pinned(hostname: str) -> str:
    """Return a TTL-cached, allowlist-validated IP for ``hostname``.

    SEC-005: the same cached IP is consumed by both :func:`_validate_url_safe`
    (pre-flight) and :class:`PinnedDNSTransport` (at connect time). The
    TOCTOU window between validation and the TCP connect collapses to a
    single resolution.
    """
    now = time.monotonic()
    cached = _dns_pin_cache.get(hostname)
    if cached and (now - cached["resolved_at"]) < DNS_PIN_TTL_SECONDS:
        return cached["ip"]

    async with _get_lock("dns"):
        # Re-check after acquiring the lock; another coroutine may have
        # just populated the cache during the wait.
        now = time.monotonic()
        cached = _dns_pin_cache.get(hostname)
        if cached and (now - cached["resolved_at"]) < DNS_PIN_TTL_SECONDS:
            return cached["ip"]

        ip = _resolve_and_validate_addrinfo(hostname)
        _dns_pin_cache[hostname] = {"ip": ip, "resolved_at": now}
        logger.debug("dns_pinned", host=hostname, ip=ip, ttl_sec=DNS_PIN_TTL_SECONDS)
        return ip


def _clear_dns_pin_cache() -> None:
    """Drop all cached DNS pins. Test-only helper."""
    _dns_pin_cache.clear()


async def _get_http_client() -> httpx.AsyncClient:
    """Return the shared httpx.AsyncClient, creating it on first call."""
    global _http_client
    if _http_client is None:
        async with _get_lock("http"):
            if _http_client is None:
                _http_client = httpx.AsyncClient(timeout=TIMEOUT)
    return _http_client


async def close_http_client() -> None:
    """Close the shared client. Called from the MCPServer lifespan teardown."""
    global _http_client, _http_lock, _token_lock, _dns_pin_lock
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None
    # Drop locks and DNS cache too — a follow-up event loop will get fresh ones.
    _http_lock = None
    _token_lock = None
    _dns_pin_lock = None
    _dns_pin_cache.clear()


def _validate_url_safe(url: str) -> None:
    """Reject ``url`` if it would expose the server to SSRF.

    Three controls are enforced before any outbound request is issued:

    1. **HTTPS-only** — ``http://``, ``file://`` and other schemes are refused.
    2. **Egress allowlist** — the hostname must appear in :data:`ALLOWED_HOSTS`.
    3. **IP blocklist** — every address the hostname resolves to is checked
       against :data:`_BLOCKED_IP_NETWORKS`; resolution to any private,
       loopback, link-local, multicast or reserved range aborts the request.

    SEC-005: the resolved IP is also written into :data:`_dns_pin_cache` so
    :class:`PinnedDNSTransport` reuses the same address at connect time. This
    closes the historical TOCTOU window where validation and the actual TCP
    connect would each call ``getaddrinfo`` and could see different IPs under
    DNS rebinding.

    Raises :class:`ValueError` on any violation. The caller (``_api_get`` /
    ``_get_access_token``) propagates the exception, which is mapped to a
    localized "Konfigurationsfehler" by :func:`_handle_error` so internal
    network details are not leaked to the MCP client.
    """
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError(f"SSRF blocked: only HTTPS is permitted for outbound requests (got scheme '{parsed.scheme}')")
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("SSRF blocked: URL has no hostname")
    if hostname not in ALLOWED_HOSTS:
        raise ValueError(f"SSRF blocked: host '{hostname}' is not in the egress allowlist ({sorted(ALLOWED_HOSTS)})")
    # SEC-005: hit the TTL'd cache first. A cached entry has already passed
    # the IP-allowlist check, so we re-trust it for the rest of the TTL
    # window — eliminating the per-request getaddrinfo call that the audit
    # finding flagged as the duplicate-resolution problem. On a miss (or
    # past-TTL) we resolve fresh, validate, and repopulate the cache.
    #
    # No asyncio.Lock here because _validate_url_safe is sync and runs in
    # event-loop coroutines. Concurrent first-time resolutions are benign:
    # both will produce the same IP from the same OS DNS layer, both will
    # validate it against _BLOCKED_IP_NETWORKS, and the last write wins.
    now = time.monotonic()
    cached = _dns_pin_cache.get(hostname)
    if cached and (now - cached["resolved_at"]) < DNS_PIN_TTL_SECONDS:
        return
    ip = _resolve_and_validate_addrinfo(hostname)
    _dns_pin_cache[hostname] = {"ip": ip, "resolved_at": now}


def parse_retry_after(resp: httpx.Response | None) -> float | None:
    """Seconds to wait per the response's ``Retry-After``, or None.

    RFC 9110 §10.2.3 allows two forms: delta-seconds (``120``) and an HTTP-date
    (``Wed, 21 Oct 2026 07:28:00 GMT``). Both appear in the wild, so both are
    read. Anything unparseable yields None and the caller falls back to its own
    curve — a malformed header must not become a crash on the error path.
    """
    if resp is None or resp.status_code not in RETRY_AFTER_STATUSES:
        return None
    raw = (resp.headers.get("Retry-After") or "").strip()
    if not raw:
        return None
    if raw.isdigit():
        return float(raw)
    try:
        when = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if when is None:
        return None
    if when.tzinfo is None:  # RFC 9110 dates are GMT; a naive one means UTC
        when = when.replace(tzinfo=UTC)
    # Never negative: a date in the past means "now".
    return max(0.0, (when - datetime.now(UTC)).total_seconds())


def retry_delay(attempt: int, last_error: Exception | None) -> float:
    """Seconds to wait before ``attempt`` (ARCH-014).

    The gateway's own answer beats our guess: if it sent ``Retry-After`` on a
    429 or 503, that value wins over the exponential curve. Everything is
    capped and spread — see the constants above for why each matters.
    """
    hinted = parse_retry_after(getattr(last_error, "response", None))
    if hinted is not None:
        jittered = hinted * (1.0 + random.random() * RETRY_AFTER_JITTER)
    else:
        jittered = RETRY_BACKOFF_BASE**attempt * (1.0 - RETRY_JITTER_SPREAD + random.random() * 2 * RETRY_JITTER_SPREAD)
    # Cap *after* jitter. The other order made RETRY_MAX_DELAY not a bound at
    # all: a value capped at 20s was then multiplied by up to 1.5 and landed at
    # 30s. The constant claimed a ceiling it did not hold.
    return min(jittered, RETRY_MAX_DELAY)


async def _request_with_retry(
    method: str,
    url: str,
    *,
    params: dict | None = None,
    headers: dict | None = None,
    deadline: float | None = None,
) -> httpx.Response:
    """Issue a request, retrying what is worth retrying (ARCH-014).

    Retried: network errors, timeouts, 5xx and 429. Not retried: any other 4xx
    — that is a statement about the request, not about the moment — and
    :class:`ValueError` from the SSRF guard or :func:`_raise_for_redirect`,
    which are configuration faults that repeat identically.

    ``deadline`` is a :func:`time.monotonic` timestamp shared with the caller,
    so a token refresh and the request it authorises spend one budget between
    them rather than one each.
    """
    if deadline is None:
        deadline = time.monotonic() + RETRY_TOTAL_BUDGET
    client = await _get_http_client()
    last_exc: Exception | None = None

    for attempt in range(RETRY_ATTEMPTS):
        if attempt > 0:
            delay = retry_delay(attempt, last_exc)
            # A wait that outlasts the budget is a wait for nobody: the caller
            # has given up by the time it ends.
            if delay >= deadline - time.monotonic():
                break
            logger.info(
                "http_retry",
                attempt=attempt + 1,
                of=RETRY_ATTEMPTS,
                delay_sec=round(delay, 2),
                exc_type=type(last_exc).__name__,
            )
            await _sleep(delay)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            # httpx applies its timeout per operation (connect/read/write/pool)
            # and the read timeout restarts with every chunk — that bounds each
            # step, not the call, so a slowly trickling response could outlast
            # the budget without any single read timing out. asyncio.timeout is
            # the wall-clock deadline the budget actually promises; the httpx
            # timeout stays alongside as the finer per-operation bound.
            async with asyncio.timeout(remaining):
                resp = await client.request(
                    method,
                    url,
                    params=params,
                    headers=headers,
                    timeout=min(TIMEOUT, remaining),
                )
                _raise_for_redirect(resp)
                resp.raise_for_status()
                return resp
        except TimeoutError as e:  # budget gone, not just this attempt
            last_exc = e
            break
        except httpx.HTTPStatusError as e:
            last_exc = e
            if e.response.status_code != 429 and 400 <= e.response.status_code < 500:
                raise
        except httpx.RequestError as e:
            last_exc = e

    if last_exc is None:  # budget gone before a single request went out
        raise httpx.ConnectTimeout(f"No attempt possible: {RETRY_TOTAL_BUDGET:g}s budget already spent")
    raise last_exc


def _get_credentials() -> tuple[str, str]:
    return get_settings().require_credentials()


async def _get_access_token(deadline: float | None = None) -> str:
    """Returns a valid OAuth2 access token, refreshing if necessary.

    ``deadline`` is passed through to the refresh so the token round-trip and
    the request that needs it share one budget instead of one each.
    """
    now = time.time()
    if _token_cache["access_token"] and _token_cache["expires_at"] > now + 60:
        logger.debug("oauth_token_cache_hit")
        return _token_cache["access_token"]

    # Serialise concurrent first-time refreshes — without this lock, a fan-out
    # via asyncio.gather on a cold cache would hammer the OAuth endpoint
    # with N parallel refresh requests.
    async with _get_lock("token"):
        # Re-check after acquiring the lock; another coroutine may have just
        # populated the cache while we were waiting.
        now = time.time()
        if _token_cache["access_token"] and _token_cache["expires_at"] > now + 60:
            logger.debug("oauth_token_cache_hit")
            return _token_cache["access_token"]

        key, secret = _get_credentials()
        credentials = base64.b64encode(f"{key}:{secret}".encode()).decode()

        _validate_url_safe(TOKEN_URL)
        logger.info("oauth_token_refresh")
        # A token endpoint that is briefly unreachable used to fail every tool
        # call outright, and a 401 from an expired-and-unrefreshable token
        # reads to the user as "wrong credentials" — a diagnosis that sends
        # them to check a key that was never the problem.
        resp = await _request_with_retry(
            "POST",
            TOKEN_URL,
            params={"grant_type": "client_credentials"},
            headers={
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": USER_AGENT,
            },
            deadline=deadline,
        )
        data = resp.json()

        _token_cache["access_token"] = data["access_token"]
        expires_in = int(data.get("expires_in", 3600))
        _token_cache["expires_at"] = now + expires_in
        logger.info("oauth_token_acquired", expires_in=expires_in)
        return _token_cache["access_token"]


def _raise_for_redirect(resp: httpx.Response) -> None:
    """Turn a gateway redirect into a diagnosis.

    An unregistered basepath is answered with ``302`` to
    ``developer.srgssr.ch`` rather than ``404``. httpx's
    ``raise_for_status()`` does raise on 3xx, so this is not about an
    unhandled response — it is about what the caller was told. That path fell
    through to the generic branch of :func:`_handle_error` and produced
    ``API-Fehler 302:`` followed by the redirect's empty body: a status code
    and nothing else, with no mention of which endpoint or why.

    Four dead basepaths (``/video/v3``, ``/audio/v3``,
    ``/forecasts/v2.0/weather``, ``/polis/v1``) survived a release behind that
    message. Naming the path and the redirect target turns it into something
    actionable. :class:`ValueError` maps to "Konfigurationsfehler", which is
    what a basepath that no longer exists actually is.
    """
    if not 300 <= resp.status_code < 400:
        return
    location = resp.headers.get("location", "(keine Location)")
    path = resp.request.url.path if resp.request else "(unbekannt)"
    logger.error(
        "gateway_redirect",
        status=resp.status_code,
        path=path,
        location=location,
    )
    raise ValueError(
        f"Der Endpunkt '{path}' ist am API-Gateway nicht registriert — er "
        f"antwortet mit HTTP {resp.status_code} auf '{location}' statt mit "
        f"Daten. Vermutlich hat sich der Basispfad der API geändert."
    )


async def _api_get(url: str, params: dict | None = None) -> dict:
    """Authenticated GET helper returning parsed JSON.

    The deadline is opened here and handed to both the token refresh and the
    request, so the whole call — not each half — is what the budget bounds.
    """
    _validate_url_safe(url)
    deadline = time.monotonic() + RETRY_TOTAL_BUDGET
    token = await _get_access_token(deadline=deadline)
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    }
    resp = await _request_with_retry("GET", url, params=params, headers=headers, deadline=deadline)
    return resp.json()


async def _safe_api_get(url: str, params: dict | None = None, not_found_hint: str | None = None) -> dict | str:
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
                "Fehler 403: Zugriff verweigert. Möglicherweise fehlt der Zugriff auf diese API im gewählten Produkt."
            )
        if sc == 404:
            base = "Fehler 404: Ressource nicht gefunden. Bitte ID oder Parameter prüfen."
            return f"{base}\n\n**Tipp:** {not_found_hint}" if not_found_hint else base
        if sc == 429:
            return "Fehler 429: Rate-Limit überschritten. Bitte etwas warten und erneut versuchen."
        base = f"API-Fehler {sc}: {e.response.text[:200]}"
        # A bad identifier does not always come back as 404. The EPG rejects an
        # unknown station with 400 (`400.01.004`), so a hint attached to 404
        # only would never reach the caller in the very case it was written
        # for. 400 means "your input was wrong" just as 404 does, and the hint
        # is what makes that recoverable.
        if sc == 400 and not_found_hint:
            return f"{base}\n\n**Tipp:** {not_found_hint}"
        return base
    # ``TimeoutError`` (builtin) comes from the retry loop's total budget,
    # ``httpx.TimeoutException`` from a single operation. To the caller both
    # mean the same thing: it took too long. Without the builtin case an
    # exhausted budget would fall through to "unerwarteter Fehler" — a message
    # that names no cause and suggests nothing.
    if isinstance(e, httpx.TimeoutException | TimeoutError):
        return "Fehler: Anfrage hat das Timeout überschritten. Bitte erneut versuchen."
    # Defense-in-Depth (OBS-002): never include str(e) in the user-facing
    # message — internals like resolved hostnames or socket details (gaierror)
    # would otherwise reach the LLM. Full exception incl. stacktrace is logged
    # to stderr via structlog.
    logger.error("unhandled_exception", exc_type=type(e).__name__, exc_info=e)
    return f"Unerwarteter Fehler. Details siehe Server-Log (Typ: {type(e).__name__})."


def _build_error_response(e: Exception, not_found_hint: str | None = None) -> "ToolErrorResponse":  # noqa: F821 — lazy import to keep _models -> _http acyclic
    """Wrap :func:`_handle_error`'s localised message in the typed
    :class:`ToolErrorResponse` model (SDK-002 Option A).

    Imported lazily to avoid a circular import: ``_models`` does not depend
    on ``_http`` and we want to keep it that way.
    """
    from srgssr_mcp._models import ToolErrorResponse

    return ToolErrorResponse(
        error_type=type(e).__name__,
        message=_handle_error(e, not_found_hint=not_found_hint),
    )


def _query_variants(query: str) -> list[str]:
    """Returns deduplicated query variants for fuzzy retry.

    Generates the original query plus normalized forms (ASCII-folded for
    diacritic-insensitive matching, lowercased, title-cased) so that a search
    for "Zurich" still hits "Zürich" upstream and vice versa.
    """
    seen: set[str] = set()
    variants: list[str] = []
    folded = "".join(c for c in unicodedata.normalize("NFKD", query) if not unicodedata.combining(c))
    for v in (query, folded, query.lower(), folded.lower(), query.title(), folded.title()):
        v = v.strip()
        if v and v not in seen:
            seen.add(v)
            variants.append(v)
    return variants
