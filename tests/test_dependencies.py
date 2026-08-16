"""Declared dependencies match what the code actually imports.

`fastmcp` was declared here long after it stopped being needed: this server
once received `mcp` transitively through it, then `mcp` was declared directly
and the `fastmcp` line was never removed. Nothing in `src/` or `tests/`
imported it, so it pulled a whole second MCP framework into every install for
no benefit — and nothing failed, which is why it survived.

These tests close both directions of that gap:

* if `fastmcp` is imported again, the missing declaration is caught here rather
  than by an ImportError in someone's fresh install;
* if the declaration comes back without an import, that is caught too.
"""

from __future__ import annotations

import pathlib
import re

import pytest

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_IMPORT_RE = re.compile(r"^\s*(?:import|from)\s+([A-Za-z_][\w.]*)", re.MULTILINE)

# Ways a step installs a package on its own. The first version of the check
# below matched the literal string "pip install ruff" and so let through
# `pip install --upgrade ruff==…`, `pip install "ruff==…"`, `pip3 install`,
# `uv tool install` and `uv run --with ruff==…` — every one of which overrides
# the pin just as effectively. A Codex review caught this, not the counter-test.
_INSTALL_FORM = re.compile(
    r"(?:pip3?\s+install|python\s+-m\s+pip\s+install|uv\s+pip\s+install"
    r"|uv\s+tool\s+install|uv\s+add|pipx\s+install|--with)\b"
)
# ruff as a package argument of its own. Quotes are allowed; a preceding word,
# path or dash character is not, or `ruff-lsp` and `scripts/ruff_helper.py`
# would count.
_RUFF_PACKAGE = re.compile(r"""(?<![\w./-])["']?ruff(?![\w-])""")


def _installs_ruff(line: str) -> bool:
    """Does this line install ruff as a named package?

    `pip install -e ".[dev]"` pulls ruff in as well — but that is the intended
    route and must not trigger. What matters is whether a separate `ruff`
    argument follows the install command.
    """
    hit = _INSTALL_FORM.search(line)
    return bool(hit) and bool(_RUFF_PACKAGE.search(line[hit.end() :]))


def _workflow_files() -> list[pathlib.Path]:
    """Both extensions: GitHub loads `*.yml` AND `*.yaml`."""
    workflows = _ROOT / ".github" / "workflows"
    return sorted([*workflows.glob("*.yml"), *workflows.glob("*.yaml")])


def _declared_dependencies() -> list[str]:
    """Distribution names from `[project].dependencies`, extras stripped."""
    import tomllib

    data = tomllib.loads((_ROOT / "pyproject.toml").read_text())
    names = []
    for spec in data["project"]["dependencies"]:
        # "mcp[cli]>=2.0.0,<3" -> "mcp"
        names.append(re.split(r"[\[<>=!~;\s]", spec, maxsplit=1)[0].lower())
    return names


def _dev_dependencies() -> list[str]:
    """Raw specifiers from `[project.optional-dependencies].dev`."""
    import tomllib

    data = tomllib.loads((_ROOT / "pyproject.toml").read_text())
    return data["project"]["optional-dependencies"]["dev"]


def test_ruff_is_pinned_exactly():
    """ruff must be pinned to one version, not a range.

    It was `ruff>=0.4.0`, so `pip install -e ".[dev]"` resolved to whatever was
    newest and a local gate run disagreed with CI about which findings exist.
    A range here reintroduces exactly that.
    """
    specs = [s for s in _dev_dependencies() if re.match(r"^ruff\b", s)]
    assert len(specs) == 1, f"expected exactly one ruff specifier, found {specs}"
    assert re.fullmatch(r"ruff==\d+\.\d+\.\d+", specs[0]), (
        f"ruff must be pinned as ruff==X.Y.Z, found {specs[0]!r}. A range lets a "
        "local install and CI run different ruff versions."
    )


def test_the_ruff_pin_is_the_only_version_source():
    """No second ruff version anywhere in the CI workflows.

    A `pip install ruff==<version>` step used to run after the `[dev]` install
    and silently won over pyproject, so editing the pin there changed nothing
    in CI. If that pattern comes back, this fails.
    """
    for workflow in _workflow_files():
        # Comments are skipped on purpose: the one in ci.yml explains why this
        # step must not come back and quotes the command it forbids.
        steps = [ln for ln in workflow.read_text().splitlines() if not ln.lstrip().startswith("#")]
        offending = [ln.strip() for ln in steps if _installs_ruff(ln)]
        assert not offending, (
            f"{workflow.name} installs ruff directly ({offending}). That step runs "
            'after pip install -e ".[dev]" and overrides the pin in pyproject.'
        )


def test_the_detector_knows_the_common_install_forms():
    """The scan above is only as good as what it recognises as an install.

    Without this table the assertion is green because it does not know the
    spelling — not because none is there. That is exactly what happened: the
    first version matched the literal "pip install ruff" and missed five of the
    seven forms checked here.
    """
    must_match = [
        "run: pip install ruff==0.16.1",
        "run: pip install --upgrade ruff==0.16.1",
        'run: pip install "ruff==0.16.1"',
        "run: pip install 'ruff==0.16.1'",
        "run: pip3 install ruff==0.16.1",
        "run: python -m pip install ruff==0.16.1",
        "run: uv pip install ruff==0.16.1 --system",
        "run: uv tool install ruff==0.16.1",
        "run: uv add ruff==0.16.1",
        "run: pipx install ruff==0.16.1",
        "run: uv run --with ruff==0.16.1 ruff check src/",
        "run: pip install ruff",
        "run: pip install pytest ruff==0.16.1",
        "run: pip install ruff[extra]==0.16.1",
    ]
    must_not_match = [
        'run: pip install -e ".[dev]"',
        'run: uv pip install -e ".[dev]" --system',
        "run: ruff check src/ tests/ scripts/",
        "run: ruff format --check src/ tests/",
        "run: pip install ruff-lsp",
        "run: pip install uv",
        "run: python -m pip install --upgrade pip",
        "run: pip install build hatchling",
        "run: uv run --with pip-audit pip-audit",
        "run: python scripts/ruff_helper.py",
        "run: pip install -r requirements.txt",
        "name: Lint with ruff",
    ]
    missed = [ln for ln in must_match if not _installs_ruff(ln)]
    assert not missed, f"detector misses: {missed}"
    false_alarm = [ln for ln in must_not_match if _installs_ruff(ln)]
    assert not false_alarm, f"detector fires wrongly on: {false_alarm}"


def test_the_workflow_scan_finds_anything_at_all():
    """Guards the check above against an empty glob.

    With no files found the loop is empty and the assertion vacuously true —
    green without having read a single workflow.
    """
    workflows = _workflow_files()
    assert len(workflows) >= 2, f"workflow scan finds almost nothing: {workflows}"
    assert any("ruff check" in w.read_text() for w in workflows), (
        "no workflow calls ruff — the scan is looking in the wrong place"
    )


def _top_level_imports() -> set[str]:
    """Top-level module names imported anywhere in src/ or tests/."""
    found: set[str] = set()
    for directory in ("src", "tests"):
        for path in (_ROOT / directory).rglob("*.py"):
            for match in _IMPORT_RE.finditer(path.read_text()):
                found.add(match.group(1).split(".")[0])
    return found


def test_fastmcp_is_not_declared_while_unused():
    """The removal itself.

    Phrased as an equivalence rather than a flat "not declared", so
    reintroducing the import legitimately does not require deleting this test —
    it requires putting the declaration back.
    """
    declared = "fastmcp" in _declared_dependencies()
    imported = "fastmcp" in _top_level_imports()
    assert declared == imported, (
        "fastmcp is declared but never imported (dead dependency: it drags a "
        "second MCP framework into every install), or imported but not "
        "declared (a fresh install will fail). Keep the two in step."
        if declared != imported
        else ""
    )


def test_the_mcp_sdk_is_declared_because_it_is_imported():
    """Guards the check above against silently passing on an empty scan.

    If the import scan broke — wrong path, changed regex — every "declared ==
    imported" comparison would trivially hold. `mcp` is imported all over this
    server, so its absence here means the scanner, not the dependency, is
    wrong.
    """
    assert "mcp" in _top_level_imports(), "import scan found nothing — it is broken"
    assert "mcp" in _declared_dependencies()


@pytest.mark.parametrize("name", ["httpx", "pydantic", "pydantic_settings", "structlog"])
def test_runtime_imports_are_all_declared(name: str):
    """The other direction, for the dependencies this server really uses.

    `pydantic_settings` is the interesting one: mcp 1.x pulled it in
    transitively and mcp 2.x dropped it, so an undeclared import would have
    broken installs at exactly this migration.
    """
    if name not in _top_level_imports():
        pytest.skip(f"{name} is not imported (nothing to check)")
    declared = _declared_dependencies()
    # Distribution names use hyphens where module names use underscores.
    assert name.replace("_", "-") in declared or name in declared
