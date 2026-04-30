"""Shared pytest fixtures for srgssr-mcp tests."""
import os
import time

import pytest

from srgssr_mcp import server


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


@pytest.fixture
def live_credentials():
    """Skip live tests unless real SRG SSR credentials are present."""
    key = os.environ.get("SRGSSR_CONSUMER_KEY", "")
    secret = os.environ.get("SRGSSR_CONSUMER_SECRET", "")
    if not key or not secret:
        pytest.skip("SRGSSR_CONSUMER_KEY/SECRET not set; live tests require real credentials")
    server._token_cache["access_token"] = None
    server._token_cache["expires_at"] = 0.0
    return key, secret
