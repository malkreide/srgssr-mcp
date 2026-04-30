"""Tests for structured logging (OBS-003)."""

import json
import logging

import httpx
import pytest
import respx

from srgssr_mcp.logging_config import _RFC5424_LEVELS, configure_logging, get_logger
from srgssr_mcp.server import (
    BusinessUnit,
    VideoShowsInput,
    WeatherSearchInput,
    srgssr_video_get_shows,
    srgssr_weather_search_location,
)


@pytest.fixture(autouse=True)
def _reset_logging(caplog):
    """Configure structlog at debug level and let pytest's caplog see records."""
    configure_logging("debug")
    caplog.set_level(logging.DEBUG)
    yield


def _records_for(caplog) -> list[dict]:
    """Return structlog event dicts from caplog records.

    With :class:`structlog.stdlib.ProcessorFormatter`, structlog packages the
    event chain in ``record.msg`` as a dict; foreign stdlib logs come through
    as plain strings and are skipped.
    """
    parsed: list[dict] = []
    for record in caplog.records:
        msg = record.msg
        if isinstance(msg, dict):
            parsed.append(msg)
        else:
            try:
                parsed.append(json.loads(record.getMessage()))
            except (json.JSONDecodeError, ValueError, TypeError):
                continue
    return parsed


def test_logger_emits_json(caplog):
    log = get_logger("test")
    log.info("test_event", key="value", count=42)
    records = _records_for(caplog)
    assert any(r.get("event") == "test_event" for r in records)
    entry = next(r for r in records if r.get("event") == "test_event")
    assert entry["key"] == "value"
    assert entry["count"] == 42
    assert entry["level"] == "info"
    assert "timestamp" in entry


def test_logger_includes_timestamp_iso_utc(caplog):
    get_logger("test").info("with_time")
    entry = next(r for r in _records_for(caplog) if r.get("event") == "with_time")
    ts = entry["timestamp"]
    assert ts.endswith("Z") or ts.endswith("+00:00")


def test_rfc5424_levels_supported():
    expected = {"debug", "info", "notice", "warning", "error", "critical", "alert", "emergency"}
    assert expected.issubset(_RFC5424_LEVELS.keys())


def test_logger_bind_propagates_context(caplog):
    log = get_logger("test").bind(tool="srgssr_test", session_id="abc-123")
    log.info("tool_invoked")
    entry = next(r for r in _records_for(caplog) if r.get("event") == "tool_invoked")
    assert entry["tool"] == "srgssr_test"
    assert entry["session_id"] == "abc-123"


def test_log_level_filters_below_threshold(caplog):
    configure_logging("warning")
    caplog.clear()
    log = get_logger("test")
    log.debug("hidden_debug")
    log.info("hidden_info")
    log.warning("visible_warning")
    events = [r.get("event") for r in _records_for(caplog)]
    assert "hidden_debug" not in events
    assert "hidden_info" not in events
    assert "visible_warning" in events
    # Restore default for following tests.
    configure_logging("debug")


def test_warning_and_error_use_correct_level(caplog):
    log = get_logger("test")
    log.warning("rate_limit_approaching", quota=90)
    log.error("api_timeout", timeout_ms=5000)
    levels = {r["event"]: r["level"] for r in _records_for(caplog) if "event" in r and "level" in r}
    assert levels["rate_limit_approaching"] == "warning"
    assert levels["api_timeout"] == "error"


@respx.mock
async def test_tool_emits_invoked_and_succeeded(caplog):
    respx.get("https://api.srgssr.ch/forecasts/v2.0/weather/geolocations").mock(
        return_value=httpx.Response(
            200,
            json={"geolocationList": [{"id": "100001", "name": "Bern", "canton": "BE", "postalCode": "3000"}]},
        )
    )
    await srgssr_weather_search_location(WeatherSearchInput(query="Bern"))
    by_event = {
        r["event"]: r
        for r in _records_for(caplog)
        if r.get("tool") == "srgssr_weather_search_location"
    }
    assert "tool_invoked" in by_event
    assert "tool_succeeded" in by_event
    assert by_event["tool_succeeded"]["result_count"] == 1
    assert by_event["tool_invoked"]["query"] == "Bern"


@respx.mock
async def test_tool_emits_failure_with_error_context(caplog):
    respx.get("https://api.srgssr.ch/video/v3/srf/showList").mock(
        return_value=httpx.Response(500, text="Boom")
    )
    await srgssr_video_get_shows(VideoShowsInput(business_unit=BusinessUnit.SRF))
    failed = [
        r for r in _records_for(caplog)
        if r.get("event") == "tool_failed" and r.get("tool") == "srgssr_video_get_shows"
    ]
    assert failed, "expected a tool_failed log entry"
    entry = failed[0]
    assert entry["business_unit"] == "srf"
    assert entry["error_type"] == "HTTPStatusError"
    assert entry["level"] == "error"


def test_configure_logging_is_idempotent():
    configure_logging("info")
    configure_logging("debug")
    handlers = [h for h in logging.getLogger().handlers if getattr(h, "_srgssr_mcp_handler", False)]
    assert len(handlers) == 1
