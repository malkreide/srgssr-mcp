"""Live tests against real SRG SSR APIs (slow, nightly only).

Run with: pytest -m live

Requires SRGSSR_CONSUMER_KEY and SRGSSR_CONSUMER_SECRET env vars.
Without credentials these tests are skipped — they're never run in the
default `pytest -m "not live"` invocation that CI uses on every PR.

Focus: schema sanity. We assert that real responses still contain the
fields our markdown rendering depends on, so we'd catch upstream
schema drift before users do.
"""
import pytest

from srgssr_mcp.server import (
    AudioEpisodesInput,
    BusinessUnit,
    EpgProgramsInput,
    PolisListInput,
    PolisResultInput,
    ResponseFormat,
    VideoEpisodesInput,
    VideoLivestreamsInput,
    VideoShowsInput,
    WeatherForecastInput,
    WeatherSearchInput,
    srgssr_audio_get_episodes,
    srgssr_audio_get_livestreams,
    srgssr_audio_get_shows,
    srgssr_epg_get_programs,
    srgssr_polis_get_elections,
    srgssr_polis_get_votation_results,
    srgssr_polis_get_votations,
    srgssr_video_get_episodes,
    srgssr_video_get_livestreams,
    srgssr_video_get_shows,
    srgssr_weather_current,
    srgssr_weather_forecast_7day,
    srgssr_weather_forecast_24h,
    srgssr_weather_search_location,
)

pytestmark = [pytest.mark.live]


def _is_error(result: str) -> bool:
    return result.startswith(("Fehler", "API-Fehler", "Konfigurationsfehler", "Unerwarteter Fehler"))


# ---------------------------------------------------------------------------
# Weather
# ---------------------------------------------------------------------------

async def test_live_weather_search_location(live_credentials):
    result = await srgssr_weather_search_location(WeatherSearchInput(query="Zürich"))
    assert not _is_error(result), result
    assert "Zürich" in result or "ID:" in result


async def test_live_weather_current(live_credentials):
    result = await srgssr_weather_current(
        WeatherForecastInput(latitude=47.3769, longitude=8.5417),
    )
    assert not _is_error(result), result
    assert "Aktuelles Wetter" in result


async def test_live_weather_forecast_24h(live_credentials):
    result = await srgssr_weather_forecast_24h(
        WeatherForecastInput(latitude=47.3769, longitude=8.5417),
    )
    assert not _is_error(result), result
    assert "24-Stunden-Prognose" in result


async def test_live_weather_forecast_7day(live_credentials):
    result = await srgssr_weather_forecast_7day(
        WeatherForecastInput(latitude=47.3769, longitude=8.5417),
    )
    assert not _is_error(result), result
    assert "7-Tages-Prognose" in result


# ---------------------------------------------------------------------------
# Video
# ---------------------------------------------------------------------------

async def test_live_video_get_shows(live_credentials):
    result = await srgssr_video_get_shows(
        VideoShowsInput(business_unit=BusinessUnit.SRF, page_size=5),
    )
    assert not _is_error(result), result
    assert "TV-Sendungen" in result


async def test_live_video_get_livestreams(live_credentials):
    result = await srgssr_video_get_livestreams(
        VideoLivestreamsInput(business_unit=BusinessUnit.SRF),
    )
    assert not _is_error(result), result
    assert "Live-TV-Sender" in result


async def test_live_video_get_episodes(live_credentials):
    """Discover a real show id via the live shows endpoint, then list episodes."""
    shows_json = await srgssr_video_get_shows(
        VideoShowsInput(
            business_unit=BusinessUnit.SRF,
            page_size=5,
            response_format=ResponseFormat.JSON,
        ),
    )
    assert not _is_error(shows_json), shows_json
    import json
    payload = json.loads(shows_json)
    shows = payload.get("shows") or []
    if not shows:
        pytest.skip("Live show list returned no shows; cannot test episodes")
    show_id = shows[0].get("id")
    assert show_id, "Live show payload missing 'id' field — schema drift?"
    result = await srgssr_video_get_episodes(
        VideoEpisodesInput(
            business_unit=BusinessUnit.SRF,
            show_id=show_id,
            page_size=3,
        ),
    )
    assert not _is_error(result), result


# ---------------------------------------------------------------------------
# Audio
# ---------------------------------------------------------------------------

async def test_live_audio_get_shows(live_credentials):
    result = await srgssr_audio_get_shows(
        VideoShowsInput(business_unit=BusinessUnit.SRF, page_size=5),
    )
    assert not _is_error(result), result
    assert "Radiosendungen" in result


async def test_live_audio_get_livestreams(live_credentials):
    result = await srgssr_audio_get_livestreams(
        VideoLivestreamsInput(business_unit=BusinessUnit.SRF),
    )
    assert not _is_error(result), result
    assert "Live-Radiosender" in result


async def test_live_audio_get_episodes(live_credentials):
    shows_json = await srgssr_audio_get_shows(
        VideoShowsInput(
            business_unit=BusinessUnit.SRF,
            page_size=5,
            response_format=ResponseFormat.JSON,
        ),
    )
    assert not _is_error(shows_json), shows_json
    import json
    payload = json.loads(shows_json)
    shows = payload.get("shows") or []
    if not shows:
        pytest.skip("Live audio show list returned no shows; cannot test episodes")
    show_id = shows[0].get("id")
    assert show_id, "Live audio show payload missing 'id' field — schema drift?"
    result = await srgssr_audio_get_episodes(
        AudioEpisodesInput(
            business_unit=BusinessUnit.SRF,
            show_id=show_id,
            page_size=3,
        ),
    )
    assert not _is_error(result), result


# ---------------------------------------------------------------------------
# EPG
# ---------------------------------------------------------------------------

async def test_live_epg_get_programs(live_credentials):
    from datetime import date, timedelta
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    result = await srgssr_epg_get_programs(
        EpgProgramsInput(
            business_unit=BusinessUnit.SRF,
            channel_id="srf1",
            date=yesterday,
        ),
    )
    assert not _is_error(result), result
    assert "Programm" in result


# ---------------------------------------------------------------------------
# Polis
# ---------------------------------------------------------------------------

async def test_live_polis_get_votations(live_credentials):
    result = await srgssr_polis_get_votations(
        PolisListInput(year_from=2020, year_to=2024, page_size=5),
    )
    assert not _is_error(result), result
    assert "Volksabstimmungen" in result


async def test_live_polis_get_elections(live_credentials):
    result = await srgssr_polis_get_elections(
        PolisListInput(year_from=2020, year_to=2024, page_size=5),
    )
    assert not _is_error(result), result
    assert "Wahlen" in result


async def test_live_polis_get_votation_results(live_credentials):
    """Discover a real votation id, then fetch its results."""
    votations_json = await srgssr_polis_get_votations(
        PolisListInput(
            year_from=2020,
            year_to=2024,
            page_size=5,
            response_format=ResponseFormat.JSON,
        ),
    )
    assert not _is_error(votations_json), votations_json
    import json
    payload = json.loads(votations_json)
    votations = payload.get("votations") or []
    if not votations:
        pytest.skip("Live votations list returned empty; cannot test results")
    votation_id = votations[0].get("id")
    assert votation_id, "Live votation payload missing 'id' field — schema drift?"
    result = await srgssr_polis_get_votation_results(
        PolisResultInput(votation_id=str(votation_id)),
    )
    assert not _is_error(result), result
