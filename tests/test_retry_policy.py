"""Retry policy toward the SRG SSR API gateway (ARCH-014).

Four questions this file answers: what is retried, how fast, how long, and
whether the ceilings the constants claim are ceilings the code holds.
"""

import time

import httpx
import pytest
import respx

from srgssr_mcp import _http as h
from srgssr_mcp._http import (
    RETRY_ATTEMPTS,
    RETRY_MAX_DELAY,
    RETRY_TOTAL_BUDGET,
    TOKEN_URL,
    WEATHER_BASE,
)

URL = f"{WEATHER_BASE}/geolocations"


def _resp(status: int, retry_after: str | None = None) -> httpx.Response:
    headers = {"Retry-After": retry_after} if retry_after is not None else {}
    return httpx.Response(status, headers=headers)


def _status_error(status: int, retry_after: str | None = None) -> httpx.HTTPStatusError:
    return httpx.HTTPStatusError("boom", request=None, response=_resp(status, retry_after))


# --- What is retried --------------------------------------------------------


@respx.mock
async def test_retries_a_503_then_succeeds():
    route = respx.get(URL).mock(side_effect=[httpx.Response(503), httpx.Response(200, json={})])
    await h._api_get(URL)
    assert route.call_count == 2


@respx.mock
async def test_retries_a_connect_error():
    route = respx.get(URL).mock(side_effect=[httpx.ConnectError(""), httpx.Response(200, json={})])
    await h._api_get(URL)
    assert route.call_count == 2


@respx.mock
async def test_a_404_fails_fast_without_retry():
    """A 4xx is a statement about the request, not about the moment."""
    route = respx.get(URL).mock(return_value=httpx.Response(404))
    with pytest.raises(httpx.HTTPStatusError):
        await h._api_get(URL)
    assert route.call_count == 1


@respx.mock
async def test_a_429_is_retried_although_it_is_a_4xx():
    route = respx.get(URL).mock(side_effect=[httpx.Response(429), httpx.Response(200, json={})])
    await h._api_get(URL)
    assert route.call_count == 2


@respx.mock
async def test_attempts_are_bounded():
    route = respx.get(URL).mock(return_value=httpx.Response(503))
    with pytest.raises(httpx.HTTPStatusError):
        await h._api_get(URL)
    assert route.call_count == RETRY_ATTEMPTS


@respx.mock
async def test_a_gateway_redirect_is_not_retried():
    """An unregistered basepath answers 302 forever — repeating it changes nothing.

    ``_raise_for_redirect`` turns it into a ``ValueError`` ("Konfigurationsfehler"),
    which the loop must let through rather than treat as a transient fault.
    """
    route = respx.get(URL).mock(return_value=httpx.Response(302, headers={"location": "https://developer.srgssr.ch"}))
    with pytest.raises(ValueError, match="nicht registriert"):
        await h._api_get(URL)
    assert route.call_count == 1


# --- How fast ---------------------------------------------------------------


class TestRetryDelay:
    def test_retry_after_seconds_beats_the_curve(self):
        """The header sits outside anything the curve can reach at this attempt."""
        exc = _status_error(503, "13")
        for _ in range(20):
            assert h.retry_delay(1, exc) >= 13.0

    def test_retry_after_http_date_is_read(self):
        """RFC 9110 allows both forms; a date is not an exception to handle later."""
        from datetime import UTC, datetime, timedelta
        from email.utils import format_datetime

        when = datetime.now(UTC) + timedelta(seconds=12)
        exc = _status_error(503, format_datetime(when, usegmt=True))
        assert 9.0 <= h.retry_delay(1, exc) <= 16.0

    @pytest.mark.parametrize("bad", ["tomorrow", "", "-5", "12.5"])
    def test_an_unparseable_retry_after_falls_back_to_the_curve(self, bad):
        """A malformed header must not become a crash on the error path."""
        exc = _status_error(503, bad)
        assert h.retry_delay(1, exc) <= 3.0

    def test_retry_after_on_a_404_is_ignored(self):
        """Only 429 and 503 carry a meaningful Retry-After per RFC 9110."""
        assert h.retry_delay(1, _status_error(404, "600")) <= 3.0

    def test_the_delay_is_spread(self):
        draws = {h.retry_delay(1, None) for _ in range(30)}
        assert len(draws) > 1, "delay is deterministic — jitter is missing"
        assert all(1.0 <= d <= 3.0 for d in draws)

    def test_retry_after_jitter_never_goes_below_the_hinted_value(self):
        """Coming back early would ignore the very header we just read."""
        exc = _status_error(429, "5")
        for _ in range(30):
            assert h.retry_delay(1, exc) >= 5.0

    def test_the_cap_is_a_real_bound_not_a_midpoint(self):
        """RETRY_MAX_DELAY must hold even when jitter swings up.

        Capping before jitter let a 20s ceiling grow to 30s on the exponential
        path and 25s on the Retry-After path. Found by a Codex review on
        parlament-mcp#35, on this same pattern.
        """
        exc = _status_error(429, "86400")
        for attempt in range(8):
            for _ in range(20):
                assert h.retry_delay(attempt, None) <= RETRY_MAX_DELAY
                assert h.retry_delay(attempt, exc) <= RETRY_MAX_DELAY

    def test_an_absurd_retry_after_lands_exactly_on_the_cap(self):
        assert h.retry_delay(0, _status_error(503, "86400")) == RETRY_MAX_DELAY


# --- How long ---------------------------------------------------------------


def test_the_budget_stays_under_the_mcp_client_default():
    """The anchor is measured, not guessed."""
    from mcp.shared._httpx_utils import MCP_DEFAULT_TIMEOUT

    assert RETRY_TOTAL_BUDGET < MCP_DEFAULT_TIMEOUT


@respx.mock
async def test_a_wait_that_outlasts_the_budget_is_not_taken(monkeypatch):
    """A wait the caller will not be around for is a wait for nobody."""
    monkeypatch.setattr(h, "RETRY_MAX_DELAY", 3600.0)  # rule out the cap as the reason
    route = respx.get(URL).mock(return_value=_resp(503, "3600"))
    with pytest.raises(httpx.HTTPStatusError):
        await h._api_get(URL)
    assert route.call_count == 1, "no time left after the first 503"


@respx.mock
async def test_a_slow_response_is_cut_by_the_wall_clock_deadline(monkeypatch, real_sleep):
    """The budget must bind even when the httpx timeout never fires.

    httpx applies its timeout per operation and the read timeout restarts with
    every chunk, so a slowly trickling answer can outlast the budget without
    any single read timing out.

    Deliberately using the *real* sleep: a clock that only advances when
    something sleeps cannot refute a guarantee about real time — that blind
    spot is exactly what let this defect through in the sibling servers.
    """
    monkeypatch.setattr(h, "RETRY_TOTAL_BUDGET", 0.05)

    async def _slow(request):
        await real_sleep(1.0)
        return httpx.Response(200, json={})

    respx.get(URL).mock(side_effect=_slow)
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        await h._api_get(URL)
    elapsed = time.monotonic() - started
    assert elapsed < 0.5, f"deadline did not cut: {elapsed:.2f}s"


def test_an_exhausted_budget_reads_as_a_timeout_not_an_unexpected_error():
    """The budget raises the builtin TimeoutError, not an httpx one.

    Without the builtin case in _handle_error an exhausted budget fell into
    "Unerwarteter Fehler" — a message that names no cause and suggests nothing.
    """
    assert "Timeout" in h._handle_error(TimeoutError())


# --- One budget for the token refresh and the request it authorises ---------


@respx.mock
async def test_the_token_refresh_and_the_request_share_one_budget(monkeypatch, real_sleep):
    """A cold cache must not buy a second full budget.

    Two independent budgets would let the token spend 25s and the call another
    25s — 50s against a 30s client default, with each half looking innocent on
    its own. The deadline is therefore opened in ``_api_get`` and handed down.

    The token here *succeeds* but eats most of the budget. What is left is too
    little for the request, so the request must be cut short.

    A failing token would not discriminate: it aborts the call under either
    design. Only a slow-but-successful one separates them — with two budgets
    the request gets a fresh full one and simply succeeds.
    """
    h._token_cache["access_token"] = None
    h._token_cache["expires_at"] = 0.0
    monkeypatch.setattr(h, "RETRY_TOTAL_BUDGET", 1.0)
    monkeypatch.setattr(h, "_get_credentials", lambda: ("key", "secret"))

    async def _slow_token(request):
        await real_sleep(0.7)
        return httpx.Response(200, json={"access_token": "t", "expires_in": 3600})

    async def _slow_api(request):
        await real_sleep(0.6)
        return httpx.Response(200, json={"ok": True})

    respx.post(TOKEN_URL).mock(side_effect=_slow_token)
    respx.get(URL).mock(side_effect=_slow_api)

    # 0.7s spent on the token leaves 0.3s — less than the 0.6s the request
    # needs. Shared: cut. Separate: the request would get a fresh 1.0s and win.
    with pytest.raises(TimeoutError):
        await h._api_get(URL)


@respx.mock
async def test_the_token_endpoint_is_retried(monkeypatch):
    """A briefly unreachable token endpoint used to fail every tool call outright."""
    h._token_cache["access_token"] = None
    h._token_cache["expires_at"] = 0.0
    monkeypatch.setattr(h, "_get_credentials", lambda: ("key", "secret"))

    token_route = respx.post(TOKEN_URL).mock(
        side_effect=[
            httpx.Response(503),
            httpx.Response(200, json={"access_token": "t", "expires_in": 3600}),
        ]
    )
    respx.get(URL).mock(return_value=httpx.Response(200, json={"ok": True}))

    assert await h._api_get(URL) == {"ok": True}
    assert token_route.call_count == 2


@respx.mock
async def test_bad_credentials_still_fail_fast(monkeypatch):
    """A 401 from the token endpoint is not transient — retrying it just waits."""
    h._token_cache["access_token"] = None
    h._token_cache["expires_at"] = 0.0
    monkeypatch.setattr(h, "_get_credentials", lambda: ("key", "secret"))
    token_route = respx.post(TOKEN_URL).mock(return_value=httpx.Response(401))

    with pytest.raises(httpx.HTTPStatusError):
        await h._api_get(URL)
    assert token_route.call_count == 1
