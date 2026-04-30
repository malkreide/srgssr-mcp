"""Structured logging configuration (OBS-003).

Wires :mod:`structlog` to emit JSON-encoded events with RFC 5424 severity
levels. Logs are routed through stdlib :mod:`logging` to ``stderr`` so the
stdio transport (which uses ``stdout`` for JSON-RPC) stays clean.

All tools obtain a logger via :func:`get_logger` and bind per-call context
(``tool``, ``session_id``, …) before emitting events, so logs are searchable
in aggregators like Datadog/Splunk/Loki without regex parsing.
"""

import logging
import os
import sys

import structlog

_RFC5424_LEVELS = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "notice": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
    "critical": logging.CRITICAL,
    "alert": logging.CRITICAL,
    "emergency": logging.CRITICAL,
}

_configured = False


def _resolve_level(level: str | int | None) -> int:
    if isinstance(level, int):
        return level
    if not level:
        env = os.environ.get("SRGSSR_LOG_LEVEL", "info")
        level = env
    return _RFC5424_LEVELS.get(level.lower(), logging.INFO)


def configure_logging(level: str | int | None = None) -> None:
    """Configure :mod:`structlog` with JSON output on stderr.

    Idempotent — repeated calls reconfigure the level but do not re-add
    handlers, so test suites that import the server module multiple times
    don't accumulate duplicate output. Foreign library logs (httpx, mcp, …)
    are routed through the same JSON formatter via
    :class:`structlog.stdlib.ProcessorFormatter`.
    """
    global _configured

    resolved_level = _resolve_level(level)

    shared_processors = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(),
        ],
    )

    root = logging.getLogger()
    root.setLevel(resolved_level)

    if not any(getattr(h, "_srgssr_mcp_handler", False) for h in root.handlers):
        handler = logging.StreamHandler(sys.stderr)
        handler._srgssr_mcp_handler = True  # type: ignore[attr-defined]
        root.addHandler(handler)

    for h in root.handlers:
        if getattr(h, "_srgssr_mcp_handler", False):
            h.setFormatter(formatter)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(resolved_level),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    _configured = True


def get_logger(name: str = "mcp.srgssr") -> structlog.stdlib.BoundLogger:
    """Return a bound structlog logger; configures defaults on first use."""
    if not _configured:
        configure_logging()
    return structlog.get_logger(name)
