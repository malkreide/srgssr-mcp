"""SRG SSR MCP Server – Swiss public media APIs."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _distribution_version

try:
    # Read the version from the installed distribution metadata, which is built
    # from pyproject.toml. Hand-maintained literals had drifted three ways:
    # pyproject said 1.0.3, this said 0.1.0, and the User-Agent in _http.py said
    # 1.0.0. A value nobody has to remember to bump cannot go stale.
    __version__ = _distribution_version("srgssr-mcp")
except PackageNotFoundError:
    # Running from the source tree without an install. Deliberately not a
    # plausible-looking number: an obviously non-release marker is better than a
    # wrong version in the User-Agent.
    __version__ = "0.0.0+source"
