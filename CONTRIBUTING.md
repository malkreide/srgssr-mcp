# Contributing to srgssr-mcp

Thank you for your interest in contributing to this project! This MCP server is part of the [Swiss Public Data MCP Portfolio](https://github.com/malkreide) and follows shared conventions across the portfolio.

[🇩🇪 Deutsche Version](CONTRIBUTING.de.md)

---

## Table of Contents

- [Reporting Issues](#reporting-issues)
- [Development Setup](#development-setup)
- [Making Changes](#making-changes)
- [Code Style](#code-style)
- [Testing](#testing)
- [Submitting a Pull Request](#submitting-a-pull-request)
- [Data Sources & Attribution](#data-sources--attribution)

---

## Reporting Issues

Before opening an issue, please check [existing issues](https://github.com/malkreide/srgssr-mcp/issues) to avoid duplicates.

When reporting a bug, please include:

- A clear description of the problem
- Steps to reproduce
- Expected vs. actual behaviour
- Python version and OS
- Relevant error messages or logs

For API-related issues (e.g. endpoint changes at developer.srgssr.ch), please note that this server depends on external SRG SSR APIs that may change without notice.

---

## Development Setup

```bash
# 1. Clone the repository
git clone https://github.com/malkreide/srgssr-mcp.git
cd srgssr-mcp

# 2. Install in editable mode with dev dependencies
pip install -e ".[dev]"

# 3. Set API credentials
export SRGSSR_CONSUMER_KEY="your-consumer-key"
export SRGSSR_CONSUMER_SECRET="your-consumer-secret"

# 4. Verify the server starts
python -m srgssr_mcp.server
```

**Requirements:**
- Python 3.11+
- API keys from [developer.srgssr.ch](https://developer.srgssr.ch) (free registration, required for live tests)

---

## Making Changes

1. **Fork** the repository and create a feature branch:
   ```bash
   git checkout -b feat/your-feature-name
   ```

2. Follow the [Conventional Commits](https://www.conventionalcommits.org/) format:

   | Type | When to use |
   |---|---|
   | `feat` | New tool or capability |
   | `fix` | Bug fix |
   | `docs` | Documentation only |
   | `refactor` | Code restructuring, no behaviour change |
   | `test` | Adding or updating tests |
   | `chore` | Build, dependencies, CI |

3. Update `CHANGELOG.md` under `[Unreleased]` for any user-visible change.

4. If you add a new tool, update both `README.md` and `README.de.md` accordingly.

---

## Code Style

This project uses [Ruff](https://docs.astral.sh/ruff/) for linting and formatting.

```bash
# Check for linting issues
ruff check src/

# Auto-fix where possible
ruff check src/ --fix

# Format code
ruff format src/
```

The CI pipeline runs Ruff on every push – PRs with linting errors will not be merged.

**General conventions:**
- Type hints on all public functions
- Pydantic v2 for data validation
- `httpx` for async HTTP calls
- Descriptive tool descriptions (they are read by the AI model)

---

## Testing

```bash
# Unit tests only (no network required)
PYTHONPATH=src pytest tests/ -m "not live"

# Integration tests (requires SRG SSR API keys)
PYTHONPATH=src pytest tests/ -m "live"

# Full suite
PYTHONPATH=src pytest tests/
```

Tests are marked with `@pytest.mark.live` when they call external APIs. The CI pipeline runs only non-live tests to avoid flakiness from external dependencies.

When adding a new tool, please add at least one unit test and one live integration test.

---

## Submitting a Pull Request

1. Ensure all tests pass and Ruff reports no errors
2. Update `CHANGELOG.md`
3. Push your branch and open a pull request against `main`
4. Describe what changed and why – link any related issues

PRs that introduce breaking changes to existing tool signatures require a discussion first.

---

## Data Sources & Attribution

This server uses the SRG SSR Public API V2:

| Source | Provider | Terms |
|---|---|---|
| [developer.srgssr.ch](https://developer.srgssr.ch) | SRG SSR | Free for non-commercial use, OAuth2 required |

The SRG SSR APIs are subject to the [SRG SSR Terms of Use](https://developer.srgssr.ch). Any contribution that incorporates additional data sources must document their licence and attribution requirements here.

---

## Portfolio Context

This server is part of a coherent portfolio of Swiss open-data MCP servers. When contributing, please consider:

- **Graceful degradation**: the server should start and provide partial functionality even if some APIs are unreachable
- **Bilingual docs**: user-facing documentation changes must be reflected in both `README.md` (English) and `README.de.md` (German)
- **Consistent naming**: tool names follow the `srgssr_` prefix convention

---

Questions? Open a [GitHub Discussion](https://github.com/malkreide/srgssr-mcp/discussions) or file an issue.
