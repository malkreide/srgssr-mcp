"""Guards against the version drift that made the User-Agent lie.

Three numbers had come apart: `pyproject.toml` said 1.0.3,
`__init__.__version__` said 0.1.0, and the hard-coded `USER_AGENT` in
`_http.py` said 1.0.0. Every request to the SRG SSR APIs carried that stale
value.

These tests fail if anyone reintroduces a literal.
"""

import tomllib
from pathlib import Path

import srgssr_mcp
from srgssr_mcp import _http

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def _pyproject_version() -> str:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]["version"]


def test_version_matches_pyproject():
    assert srgssr_mcp.__version__ == _pyproject_version()


def test_user_agent_carries_the_real_version():
    expected = f"srgssr-mcp/{_pyproject_version()} (github.com/malkreide/srgssr-mcp)"
    assert _http.USER_AGENT == expected


def test_user_agent_is_not_a_source_checkout_marker():
    assert "+source" not in _http.USER_AGENT
