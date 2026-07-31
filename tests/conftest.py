"""Shared pytest fixtures for srgssr-mcp tests."""
import os
import time

import pytest

from srgssr_mcp import server
from srgssr_mcp._http import close_http_client


@pytest.fixture(autouse=True)
def _preseed_oauth_token():
    """Inject a fake bearer token so unit tests skip the OAuth round-trip.

    The server's `_get_access_token` short-circuits when `_token_cache`
    contains a non-expired token, so respx never sees the token endpoint
    and tests don't need real credentials.
    """
    server._token_cache["access_token"] = "test-token"
    server._token_cache["expires_at"] = time.time() + 3600
    yield
    server._token_cache["access_token"] = None
    server._token_cache["expires_at"] = 0.0


@pytest.fixture(autouse=True)
def _reset_dns_pin_cache():
    """SEC-005: drop any cached DNS pins between tests.

    Tests that monkeypatch ``socket.getaddrinfo`` to return a blocked IP
    (e.g. ``test_validate_url_safe_rejects_private_rfc1918_ip``) would see
    a stale cache hit from a previous test and bypass the monkeypatched
    resolver, masking the regression we are trying to detect.
    """
    from srgssr_mcp import _http as _http_mod

    _http_mod._dns_pin_cache.clear()
    yield
    _http_mod._dns_pin_cache.clear()


@pytest.fixture(autouse=True)
async def _reset_http_client():
    """Close the shared httpx client between tests.

    ``_http_client`` is created once and held for the process lifetime, which
    is right for a server but wrong under pytest-asyncio: every test gets a
    fresh event loop, so the second test inherits a client whose pooled
    connections belong to a loop that is already closed. The next request dies
    with ``RuntimeError: Event loop is closed`` — an error that looks like a
    broken API and is nothing of the sort.

    Only live tests hit the network, so only they were affected, and only
    intermittently, depending on whether a pooled connection happened to be
    reused. Closing the client per test removes the guesswork.
    """
    yield
    await close_http_client()


@pytest.fixture
def live_credentials():
    """Skip live tests unless real SRG SSR credentials are present.

    Deliberately returns nothing. pytest prints every fixture value in its
    failure reports, so returning the key and secret here put both in plain
    text at the top of any failing live-test output — and those reports get
    pasted into issues and chats. No test needs the values; the tools read
    them from the environment themselves.
    """
    if not os.environ.get("SRGSSR_CONSUMER_KEY") or not os.environ.get(
        "SRGSSR_CONSUMER_SECRET"
    ):
        pytest.skip("SRGSSR_CONSUMER_KEY/SECRET not set; live tests require real credentials")
    server._token_cache["access_token"] = None
    server._token_cache["expires_at"] = 0.0
    # Settings are memoized; drop any cached value so the live env is re-read.
    server.get_settings.cache_clear()
