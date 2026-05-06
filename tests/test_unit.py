"""Unit tests with mocked HTTP responses (fast, CI-safe).

Each tool covers three scenarios:
1. Happy path  — 200 with realistic payload, markdown rendering checked
2. Error path  — 4xx/5xx, tool returns localized error string instead of raising
3. Edge case   — empty list / JSON format / boundary input

Tools are called directly (the @mcp.tool decorator does not wrap them);
input is constructed via the Pydantic models from server.py.
"""
import asyncio
import json

import httpx
import pytest
import respx

from srgssr_mcp.server import (
    AudioEpisodesInput,
    BusinessUnit,
    DailyBriefingInput,
    EpgProgramsInput,
    PolisListInput,
    PolisResultInput,
    ResponseFormat,
    VideoEpisodesInput,
    VideoLivestreamsInput,
    VideoShowsInput,
    WeatherForecastInput,
    WeatherSearchInput,
    mcp,
    srgssr_audio_get_episodes,
    srgssr_audio_get_livestreams,
    srgssr_audio_get_shows,
    srgssr_daily_briefing,
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

WEATHER_BASE = "https://api.srgssr.ch/forecasts/v2.0/weather"
VIDEO_BASE = "https://api.srgssr.ch/video/v3"
AUDIO_BASE = "https://api.srgssr.ch/audio/v3"
EPG_BASE = "https://api.srgssr.ch/epg/v3"
POLIS_BASE = "https://api.srgssr.ch/polis/v1"


# ---------------------------------------------------------------------------
# Weather: search_location
# ---------------------------------------------------------------------------

@respx.mock
async def test_weather_search_location_happy_path():
    respx.get(f"{WEATHER_BASE}/geolocations").mock(
        return_value=httpx.Response(
            200,
            json={
                "geolocationList": [
                    {"id": "100001", "name": "Zürich", "canton": "ZH", "postalCode": "8001"},
                    {"id": "100002", "name": "Zürich Flughafen", "canton": "ZH", "postalCode": "8058"},
                ]
            },
        )
    )
    result = await srgssr_weather_search_location(WeatherSearchInput(query="Zürich"))
    assert "Zürich" in result
    assert "100001" in result
    assert "8001" in result


@respx.mock
async def test_weather_search_location_handles_500():
    respx.get(f"{WEATHER_BASE}/geolocations").mock(
        return_value=httpx.Response(500, text="Internal Server Error")
    )
    result = await srgssr_weather_search_location(WeatherSearchInput(query="Bern"))
    assert "Fehler" in result or "API-Fehler" in result


@respx.mock
async def test_weather_search_location_empty_results():
    respx.get(f"{WEATHER_BASE}/geolocations").mock(
        return_value=httpx.Response(200, json={"geolocationList": []})
    )
    result = await srgssr_weather_search_location(WeatherSearchInput(query="Atlantis"))
    assert "Keine Standorte gefunden" in result


# ---------------------------------------------------------------------------
# Weather: current
# ---------------------------------------------------------------------------

@respx.mock
async def test_weather_current_happy_path():
    respx.get(f"{WEATHER_BASE}/current").mock(
        return_value=httpx.Response(
            200,
            json={
                "currentForecast": {
                    "values": {
                        "ttt": {"value": 18.5},
                        "weatherCode": {"value": 1},
                        "ff": {"value": 12},
                        "dd": {"value": 270},
                        "rr": {"value": 0.0},
                        "relhum": {"value": 65},
                    }
                }
            },
        )
    )
    result = await srgssr_weather_current(
        WeatherForecastInput(latitude=47.3769, longitude=8.5417)
    )
    assert "Aktuelles Wetter" in result
    assert "18.5" in result


@respx.mock
async def test_weather_current_handles_429():
    respx.get(f"{WEATHER_BASE}/current").mock(
        return_value=httpx.Response(429, text="Too Many Requests")
    )
    result = await srgssr_weather_current(
        WeatherForecastInput(latitude=47.3769, longitude=8.5417)
    )
    assert "429" in result or "Rate-Limit" in result


@respx.mock
async def test_weather_current_json_format():
    payload = {"currentForecast": {"values": {"ttt": {"value": 5.0}}}}
    respx.get(f"{WEATHER_BASE}/current").mock(
        return_value=httpx.Response(200, json=payload)
    )
    result = await srgssr_weather_current(
        WeatherForecastInput(
            latitude=47.0,
            longitude=8.0,
            response_format=ResponseFormat.JSON,
        )
    )
    assert "currentForecast" in result
    assert "5.0" in result


# ---------------------------------------------------------------------------
# Weather: forecast_24h
# ---------------------------------------------------------------------------

@respx.mock
async def test_weather_forecast_24h_happy_path():
    hours = [
        {
            "dateTime": f"2026-04-30T{h:02d}:00",
            "values": {
                "ttt": {"value": 10 + h % 5},
                "rr": {"value": 0.0},
                "weatherCode": {"value": 1},
            },
        }
        for h in range(24)
    ]
    respx.get(f"{WEATHER_BASE}/24hour").mock(
        return_value=httpx.Response(200, json={"list": hours})
    )
    result = await srgssr_weather_forecast_24h(
        WeatherForecastInput(latitude=47.0, longitude=8.0)
    )
    assert "24-Stunden-Prognose" in result
    assert "2026-04-30T00:00" in result
    assert "2026-04-30T23:00" in result


@respx.mock
async def test_weather_forecast_24h_handles_404():
    respx.get(f"{WEATHER_BASE}/24hour").mock(
        return_value=httpx.Response(404, text="Not Found")
    )
    result = await srgssr_weather_forecast_24h(
        WeatherForecastInput(latitude=47.0, longitude=8.0)
    )
    assert "404" in result or "nicht gefunden" in result


@respx.mock
async def test_weather_forecast_24h_empty_falls_back_to_json_dump():
    respx.get(f"{WEATHER_BASE}/24hour").mock(
        return_value=httpx.Response(200, json={"unexpected": "shape"})
    )
    result = await srgssr_weather_forecast_24h(
        WeatherForecastInput(latitude=47.0, longitude=8.0)
    )
    assert "unexpected" in result


# ---------------------------------------------------------------------------
# Weather: forecast_7day
# ---------------------------------------------------------------------------

@respx.mock
async def test_weather_forecast_7day_happy_path():
    days = [
        {
            "dateTime": f"2026-05-{d:02d}",
            "values": {
                "ttn": {"value": 5 + d},
                "ttx": {"value": 15 + d},
                "rr": {"value": 1.2},
                "weatherCode": {"value": 2},
            },
        }
        for d in range(1, 8)
    ]
    respx.get(f"{WEATHER_BASE}/7day").mock(
        return_value=httpx.Response(200, json={"list": days})
    )
    result = await srgssr_weather_forecast_7day(
        WeatherForecastInput(latitude=47.0, longitude=8.0)
    )
    assert "7-Tages-Prognose" in result
    assert "2026-05-01" in result
    assert "2026-05-07" in result


@respx.mock
async def test_weather_forecast_7day_handles_401():
    respx.get(f"{WEATHER_BASE}/7day").mock(
        return_value=httpx.Response(401, text="Unauthorized")
    )
    result = await srgssr_weather_forecast_7day(
        WeatherForecastInput(latitude=47.0, longitude=8.0)
    )
    assert "401" in result or "Credentials" in result


@respx.mock
async def test_weather_forecast_7day_json_format():
    days = [{"dateTime": "2026-05-01", "values": {"ttn": {"value": 5}, "ttx": {"value": 15}}}]
    respx.get(f"{WEATHER_BASE}/7day").mock(
        return_value=httpx.Response(200, json={"list": days})
    )
    result = await srgssr_weather_forecast_7day(
        WeatherForecastInput(
            latitude=47.0,
            longitude=8.0,
            response_format=ResponseFormat.JSON,
        )
    )
    assert "2026-05-01" in result


# ---------------------------------------------------------------------------
# Video: get_shows
# ---------------------------------------------------------------------------

@respx.mock
async def test_video_get_shows_happy_path():
    respx.get(f"{VIDEO_BASE}/srf/showList").mock(
        return_value=httpx.Response(
            200,
            json={
                "total": 2,
                "showList": [
                    {"id": "srf-tagesschau", "title": "Tagesschau", "description": "Nachrichten"},
                    {"id": "srf-meteo", "title": "Meteo", "description": "Wetter"},
                ],
            },
        )
    )
    result = await srgssr_video_get_shows(VideoShowsInput(business_unit=BusinessUnit.SRF))
    assert "Tagesschau" in result
    assert "srf-tagesschau" in result
    assert "Meteo" in result


@respx.mock
async def test_video_get_shows_handles_403():
    respx.get(f"{VIDEO_BASE}/rts/showList").mock(
        return_value=httpx.Response(403, text="Forbidden")
    )
    result = await srgssr_video_get_shows(VideoShowsInput(business_unit=BusinessUnit.RTS))
    assert "403" in result or "verweigert" in result


@respx.mock
async def test_video_get_shows_pagination_hint():
    respx.get(f"{VIDEO_BASE}/srf/showList").mock(
        return_value=httpx.Response(
            200,
            json={"total": 100, "showList": [{"id": f"s{i}", "title": f"T{i}"} for i in range(20)]},
        )
    )
    result = await srgssr_video_get_shows(
        VideoShowsInput(business_unit=BusinessUnit.SRF, page=1, page_size=20)
    )
    assert "page=2" in result


# ---------------------------------------------------------------------------
# Video: get_episodes
# ---------------------------------------------------------------------------

@respx.mock
async def test_video_get_episodes_happy_path():
    respx.get(f"{VIDEO_BASE}/srf/showEpisodesList/srf-tagesschau").mock(
        return_value=httpx.Response(
            200,
            json={
                "total": 1,
                "episodeList": [
                    {
                        "id": "ep-001",
                        "title": "Tagesschau vom 30.04.2026",
                        "date": "2026-04-30",
                        "duration": 1500,
                        "description": "Hauptausgabe",
                    }
                ],
            },
        )
    )
    result = await srgssr_video_get_episodes(
        VideoEpisodesInput(business_unit=BusinessUnit.SRF, show_id="srf-tagesschau")
    )
    assert "Tagesschau vom 30.04.2026" in result
    assert "ep-001" in result
    assert "25 min" in result


@respx.mock
async def test_video_get_episodes_handles_404():
    respx.get(f"{VIDEO_BASE}/srf/showEpisodesList/does-not-exist").mock(
        return_value=httpx.Response(404, text="Not Found")
    )
    result = await srgssr_video_get_episodes(
        VideoEpisodesInput(business_unit=BusinessUnit.SRF, show_id="does-not-exist")
    )
    assert "404" in result or "nicht gefunden" in result


@respx.mock
async def test_video_get_episodes_empty_list():
    respx.get(f"{VIDEO_BASE}/srf/showEpisodesList/empty-show").mock(
        return_value=httpx.Response(200, json={"total": 0, "episodeList": []})
    )
    result = await srgssr_video_get_episodes(
        VideoEpisodesInput(business_unit=BusinessUnit.SRF, show_id="empty-show")
    )
    assert "empty-show" in result


# ---------------------------------------------------------------------------
# Video: get_livestreams
# ---------------------------------------------------------------------------

@respx.mock
async def test_video_get_livestreams_happy_path():
    respx.get(f"{VIDEO_BASE}/srf/channels").mock(
        return_value=httpx.Response(
            200,
            json={"channelList": [{"id": "srf1", "title": "SRF 1"}, {"id": "srf2", "title": "SRF zwei"}]},
        )
    )
    result = await srgssr_video_get_livestreams(
        VideoLivestreamsInput(business_unit=BusinessUnit.SRF)
    )
    assert "SRF 1" in result
    assert "srf1" in result


@respx.mock
async def test_video_get_livestreams_handles_500():
    respx.get(f"{VIDEO_BASE}/rsi/channels").mock(
        return_value=httpx.Response(500, text="Server Error")
    )
    result = await srgssr_video_get_livestreams(
        VideoLivestreamsInput(business_unit=BusinessUnit.RSI)
    )
    assert "500" in result or "Fehler" in result


@respx.mock
async def test_video_get_livestreams_json_format():
    respx.get(f"{VIDEO_BASE}/rtr/channels").mock(
        return_value=httpx.Response(200, json={"channelList": [{"id": "rtr", "title": "RTR"}]})
    )
    result = await srgssr_video_get_livestreams(
        VideoLivestreamsInput(business_unit=BusinessUnit.RTR, response_format=ResponseFormat.JSON)
    )
    assert "rtr" in result
    assert "[" in result and "]" in result


# ---------------------------------------------------------------------------
# Audio: get_shows
# ---------------------------------------------------------------------------

@respx.mock
async def test_audio_get_shows_happy_path():
    respx.get(f"{AUDIO_BASE}/srf/showList").mock(
        return_value=httpx.Response(
            200,
            json={
                "total": 1,
                "showList": [{"id": "echo", "title": "Echo der Zeit", "description": "Hintergrund"}],
            },
        )
    )
    result = await srgssr_audio_get_shows(VideoShowsInput(business_unit=BusinessUnit.SRF))
    assert "Echo der Zeit" in result
    assert "echo" in result


@respx.mock
async def test_audio_get_shows_handles_401():
    respx.get(f"{AUDIO_BASE}/srf/showList").mock(
        return_value=httpx.Response(401, text="Unauthorized")
    )
    result = await srgssr_audio_get_shows(VideoShowsInput(business_unit=BusinessUnit.SRF))
    assert "401" in result or "Credentials" in result


@respx.mock
async def test_audio_get_shows_alternative_keys():
    respx.get(f"{AUDIO_BASE}/srf/showList").mock(
        return_value=httpx.Response(
            200,
            json={"shows": [{"id": "x", "name": "Alt-Format-Show", "lead": "lead-text"}]},
        )
    )
    result = await srgssr_audio_get_shows(VideoShowsInput(business_unit=BusinessUnit.SRF))
    assert "Alt-Format-Show" in result


# ---------------------------------------------------------------------------
# Audio: get_episodes
# ---------------------------------------------------------------------------

@respx.mock
async def test_audio_get_episodes_happy_path():
    respx.get(f"{AUDIO_BASE}/srf/showEpisodesList/echo").mock(
        return_value=httpx.Response(
            200,
            json={
                "episodeList": [
                    {"id": "e1", "title": "Folge 1", "date": "2026-04-30", "duration": 1800}
                ]
            },
        )
    )
    result = await srgssr_audio_get_episodes(
        AudioEpisodesInput(business_unit=BusinessUnit.SRF, show_id="echo")
    )
    assert "Folge 1" in result
    assert "e1" in result
    assert "30 min" in result


@respx.mock
async def test_audio_get_episodes_handles_429():
    respx.get(f"{AUDIO_BASE}/rts/showEpisodesList/foo").mock(
        return_value=httpx.Response(429, text="Slow down")
    )
    result = await srgssr_audio_get_episodes(
        AudioEpisodesInput(business_unit=BusinessUnit.RTS, show_id="foo")
    )
    assert "429" in result or "Rate-Limit" in result


@respx.mock
async def test_audio_get_episodes_json_format():
    respx.get(f"{AUDIO_BASE}/rts/showEpisodesList/foo").mock(
        return_value=httpx.Response(
            200,
            json={"episodeList": [{"id": "x", "title": "T", "duration": 60}]},
        )
    )
    result = await srgssr_audio_get_episodes(
        AudioEpisodesInput(
            business_unit=BusinessUnit.RTS,
            show_id="foo",
            response_format=ResponseFormat.JSON,
        )
    )
    assert "episodes" in result
    assert "\"id\"" in result


# ---------------------------------------------------------------------------
# Audio: get_livestreams
# ---------------------------------------------------------------------------

@respx.mock
async def test_audio_get_livestreams_happy_path():
    respx.get(f"{AUDIO_BASE}/srf/channels").mock(
        return_value=httpx.Response(
            200,
            json={"channelList": [{"id": "srf3", "title": "Radio SRF 3"}]},
        )
    )
    result = await srgssr_audio_get_livestreams(
        VideoLivestreamsInput(business_unit=BusinessUnit.SRF)
    )
    assert "Radio SRF 3" in result
    assert "srf3" in result


@respx.mock
async def test_audio_get_livestreams_handles_500():
    respx.get(f"{AUDIO_BASE}/swi/channels").mock(
        return_value=httpx.Response(500, text="Boom")
    )
    result = await srgssr_audio_get_livestreams(
        VideoLivestreamsInput(business_unit=BusinessUnit.SWI)
    )
    assert "500" in result or "Fehler" in result


@respx.mock
async def test_audio_get_livestreams_empty():
    respx.get(f"{AUDIO_BASE}/swi/channels").mock(
        return_value=httpx.Response(200, json={"channelList": []})
    )
    result = await srgssr_audio_get_livestreams(
        VideoLivestreamsInput(business_unit=BusinessUnit.SWI)
    )
    assert "Live-Radiosender" in result


# ---------------------------------------------------------------------------
# EPG: get_programs
# ---------------------------------------------------------------------------

@respx.mock
async def test_epg_get_programs_happy_path():
    respx.get(f"{EPG_BASE}/programs").mock(
        return_value=httpx.Response(
            200,
            json={
                "programList": [
                    {
                        "startTime": "20:00",
                        "title": "Tagesschau",
                        "subtitle": "Hauptausgabe",
                        "description": "Nachrichten",
                    },
                    {"startTime": "20:15", "title": "Meteo"},
                ]
            },
        )
    )
    result = await srgssr_epg_get_programs(
        EpgProgramsInput(business_unit=BusinessUnit.SRF, channel_id="srf1", date="2026-04-30")
    )
    assert "Tagesschau" in result
    assert "20:00" in result
    assert "Meteo" in result


@respx.mock
async def test_epg_get_programs_handles_404():
    respx.get(f"{EPG_BASE}/programs").mock(
        return_value=httpx.Response(404, text="Not Found")
    )
    result = await srgssr_epg_get_programs(
        EpgProgramsInput(business_unit=BusinessUnit.SRF, channel_id="srf1", date="2026-04-30")
    )
    assert "404" in result or "nicht gefunden" in result


def test_epg_invalid_date_format_rejected_by_pydantic():
    with pytest.raises(Exception):
        EpgProgramsInput(business_unit=BusinessUnit.SRF, channel_id="srf1", date="30-04-2026")


# ---------------------------------------------------------------------------
# Polis: get_votations
# ---------------------------------------------------------------------------

@respx.mock
async def test_polis_get_votations_happy_path():
    respx.get(f"{POLIS_BASE}/votations").mock(
        return_value=httpx.Response(
            200,
            json={
                "total": 2,
                "votationList": [
                    {"id": "v1", "title": "Bildungsinitiative", "date": "2024-09-22"},
                    {"id": "v2", "title": "Klimaschutz-Referendum", "date": "2024-11-24"},
                ],
            },
        )
    )
    result = await srgssr_polis_get_votations(PolisListInput(year_from=2024))
    assert "Bildungsinitiative" in result
    assert "v1" in result


@respx.mock
async def test_polis_get_votations_handles_500():
    respx.get(f"{POLIS_BASE}/votations").mock(
        return_value=httpx.Response(500, text="Server down")
    )
    result = await srgssr_polis_get_votations(PolisListInput())
    assert "500" in result or "Fehler" in result


@respx.mock
async def test_polis_get_votations_canton_filter_uppercased():
    route = respx.get(f"{POLIS_BASE}/votations").mock(
        return_value=httpx.Response(200, json={"total": 0, "votationList": []})
    )
    await srgssr_polis_get_votations(PolisListInput(canton="zh"))
    sent = route.calls.last.request.url
    assert "canton=ZH" in str(sent)


# ---------------------------------------------------------------------------
# Polis: get_votation_results
# ---------------------------------------------------------------------------

@respx.mock
async def test_polis_get_votation_results_happy_path():
    respx.get(f"{POLIS_BASE}/votations/v1").mock(
        return_value=httpx.Response(
            200,
            json={
                "title": "Bildungsinitiative",
                "date": "2024-09-22",
                "result": {
                    "yesPercentage": 52.3,
                    "noPercentage": 47.7,
                    "accepted": True,
                    "turnout": 45.1,
                },
                "cantonalResults": [
                    {"canton": "ZH", "yesPercentage": 55.0, "accepted": True},
                    {"canton": "BE", "yesPercentage": 48.0, "accepted": False},
                ],
            },
        )
    )
    result = await srgssr_polis_get_votation_results(PolisResultInput(votation_id="v1"))
    assert "Bildungsinitiative" in result
    assert "Angenommen" in result
    assert "52.3" in result
    assert "ZH" in result


@respx.mock
async def test_polis_get_votation_results_handles_404():
    respx.get(f"{POLIS_BASE}/votations/missing").mock(
        return_value=httpx.Response(404, text="Not Found")
    )
    result = await srgssr_polis_get_votation_results(PolisResultInput(votation_id="missing"))
    assert "404" in result or "nicht gefunden" in result


@respx.mock
async def test_polis_get_votation_results_pending_outcome():
    respx.get(f"{POLIS_BASE}/votations/v2").mock(
        return_value=httpx.Response(
            200,
            json={"title": "Pending", "date": "2026-05-01", "result": {}},
        )
    )
    result = await srgssr_polis_get_votation_results(PolisResultInput(votation_id="v2"))
    assert "Ergebnis ausstehend" in result


# ---------------------------------------------------------------------------
# Polis: get_elections
# ---------------------------------------------------------------------------

@respx.mock
async def test_polis_get_elections_happy_path():
    respx.get(f"{POLIS_BASE}/elections").mock(
        return_value=httpx.Response(
            200,
            json={
                "total": 1,
                "electionList": [
                    {"id": "e1", "title": "Nationalratswahlen 2023", "date": "2023-10-22"}
                ],
            },
        )
    )
    result = await srgssr_polis_get_elections(PolisListInput(year_from=2023))
    assert "Nationalratswahlen 2023" in result
    assert "e1" in result


@respx.mock
async def test_polis_get_elections_handles_403():
    respx.get(f"{POLIS_BASE}/elections").mock(
        return_value=httpx.Response(403, text="Forbidden")
    )
    result = await srgssr_polis_get_elections(PolisListInput())
    assert "403" in result or "verweigert" in result


@respx.mock
async def test_polis_get_elections_json_format():
    respx.get(f"{POLIS_BASE}/elections").mock(
        return_value=httpx.Response(
            200,
            json={"total": 0, "electionList": []},
        )
    )
    result = await srgssr_polis_get_elections(
        PolisListInput(response_format=ResponseFormat.JSON)
    )
    assert "elections" in result
    assert "\"total\": 0" in result


# ---------------------------------------------------------------------------
# ARCH-002: Tool description quality (length + structured tags)
# ---------------------------------------------------------------------------

async def test_tool_descriptions_meet_length_requirement():
    """Median tool-description length must be ≥100 chars (ARCH-002)."""
    tools = await mcp.list_tools()
    lengths = sorted(len(t.description or "") for t in tools)
    median = lengths[len(lengths) // 2]
    assert median >= 100, f"Median description length {median} < 100"


async def test_tool_descriptions_have_use_case_tag_coverage():
    """At least 80% of tools must carry a <use_case> tag (ARCH-002)."""
    tools = await mcp.list_tools()
    with_use_case = sum(1 for t in tools if "<use_case>" in (t.description or ""))
    coverage = with_use_case / len(tools)
    assert coverage >= 0.8, (
        f"<use_case> coverage {coverage:.0%} < 80% "
        f"({with_use_case}/{len(tools)} tools)"
    )


async def test_tool_descriptions_carry_structured_tags():
    """Every tool description must include use_case, important_notes and example tags."""
    tools = await mcp.list_tools()
    missing: list[str] = []
    for t in tools:
        desc = t.description or ""
        for tag in ("<use_case>", "<important_notes>", "<example>"):
            if tag not in desc:
                missing.append(f"{t.name} missing {tag}")
    assert not missing, "Structured tags missing:\n" + "\n".join(missing)


# ---------------------------------------------------------------------------
# ARCH-003: Fuzzy search and suggestion engines for empty results
# ---------------------------------------------------------------------------

@respx.mock
async def test_weather_search_location_fuzzy_retry_with_ascii_fold():
    """Ascii-folded variant ('Zurich') hits when original ('Zürich') misses."""
    route = respx.get(f"{WEATHER_BASE}/geolocations").mock(
        side_effect=[
            httpx.Response(200, json={"geolocationList": []}),
            httpx.Response(
                200,
                json={"geolocationList": [{"id": "100001", "name": "Zürich", "canton": "ZH", "postalCode": "8001"}]},
            ),
        ]
    )
    result = await srgssr_weather_search_location(WeatherSearchInput(query="Zürich"))
    assert "Zürich" in result
    assert "100001" in result
    # Header annotates which variant succeeded
    assert "Treffer via" in result
    assert route.call_count >= 2


@respx.mock
async def test_weather_search_location_empty_includes_suggestions():
    """All variants empty → response lists tried variants and provides hints."""
    respx.get(f"{WEATHER_BASE}/geolocations").mock(
        return_value=httpx.Response(200, json={"geolocationList": []})
    )
    result = await srgssr_weather_search_location(WeatherSearchInput(query="Atlantis"))
    assert "Keine Standorte gefunden" in result
    assert "versuchte Varianten" in result
    assert "Vorschläge" in result
    assert "PLZ" in result


@respx.mock
async def test_video_get_episodes_404_includes_recovery_hint():
    """404 on show_id includes a hint pointing to srgssr_video_get_shows."""
    respx.get(f"{VIDEO_BASE}/srf/showEpisodesList/typo-id").mock(
        return_value=httpx.Response(404, text="Not Found")
    )
    result = await srgssr_video_get_episodes(
        VideoEpisodesInput(business_unit=BusinessUnit.SRF, show_id="typo-id")
    )
    assert "404" in result
    assert "srgssr_video_get_shows" in result
    assert "typo-id" in result


@respx.mock
async def test_video_get_episodes_empty_list_includes_suggestion():
    """Empty episode list → suggests verifying show_id via srgssr_video_get_shows."""
    respx.get(f"{VIDEO_BASE}/srf/showEpisodesList/empty-show").mock(
        return_value=httpx.Response(200, json={"total": 0, "episodeList": []})
    )
    result = await srgssr_video_get_episodes(
        VideoEpisodesInput(business_unit=BusinessUnit.SRF, show_id="empty-show")
    )
    assert "Keine Episoden gefunden" in result
    assert "srgssr_video_get_shows" in result


@respx.mock
async def test_audio_get_episodes_404_includes_recovery_hint():
    respx.get(f"{AUDIO_BASE}/rts/showEpisodesList/missing").mock(
        return_value=httpx.Response(404, text="Not Found")
    )
    result = await srgssr_audio_get_episodes(
        AudioEpisodesInput(business_unit=BusinessUnit.RTS, show_id="missing")
    )
    assert "404" in result
    assert "srgssr_audio_get_shows" in result


@respx.mock
async def test_polis_get_votation_results_404_includes_recovery_hint():
    """404 on votation_id should suggest srgssr_polis_get_votations."""
    respx.get(f"{POLIS_BASE}/votations/missing").mock(
        return_value=httpx.Response(404, text="Not Found")
    )
    result = await srgssr_polis_get_votation_results(PolisResultInput(votation_id="missing"))
    assert "404" in result
    assert "srgssr_polis_get_votations" in result


@respx.mock
async def test_polis_get_votations_empty_includes_filter_suggestions():
    """Empty result with restrictive filters → response suggests loosening filters."""
    respx.get(f"{POLIS_BASE}/votations").mock(
        return_value=httpx.Response(200, json={"total": 0, "votationList": []})
    )
    result = await srgssr_polis_get_votations(
        PolisListInput(canton="GR", year_from=2020, year_to=2021)
    )
    assert "Keine Volksabstimmungen gefunden" in result
    assert "Vorschläge" in result
    # canton-Filter suggestion
    assert "canton-Filter entfernen" in result


@respx.mock
async def test_polis_get_elections_empty_includes_filter_suggestions():
    respx.get(f"{POLIS_BASE}/elections").mock(
        return_value=httpx.Response(200, json={"total": 0, "electionList": []})
    )
    result = await srgssr_polis_get_elections(
        PolisListInput(canton="ZG", year_from=2024)
    )
    assert "Keine Wahlen gefunden" in result
    assert "Vorschläge" in result


@respx.mock
async def test_epg_get_programs_404_includes_recovery_hint():
    respx.get(f"{EPG_BASE}/programs").mock(
        return_value=httpx.Response(404, text="Not Found")
    )
    result = await srgssr_epg_get_programs(
        EpgProgramsInput(business_unit=BusinessUnit.SRF, channel_id="bogus", date="2026-04-30")
    )
    assert "404" in result
    assert "srgssr_video_get_livestreams" in result


@respx.mock
async def test_video_get_shows_empty_suggests_alternative_bu():
    respx.get(f"{VIDEO_BASE}/swi/showList").mock(
        return_value=httpx.Response(200, json={"total": 0, "showList": []})
    )
    result = await srgssr_video_get_shows(VideoShowsInput(business_unit=BusinessUnit.SWI))
    assert "Keine TV-Sendungen gefunden" in result
    assert "srf" in result or "rts" in result


# ---------------------------------------------------------------------------
# ARCH-007: Capability aggregation (parallel weather + EPG fan-out)
# ---------------------------------------------------------------------------

def _briefing_input(**overrides) -> DailyBriefingInput:
    defaults = dict(
        business_unit=BusinessUnit.SRF,
        channel_id="srf1",
        date="2026-04-30",
        latitude=47.3769,
        longitude=8.5417,
    )
    defaults.update(overrides)
    return DailyBriefingInput(**defaults)


@respx.mock
async def test_daily_briefing_combines_weather_and_epg():
    """Both upstream calls succeed → markdown briefing carries both sections."""
    weather_route = respx.get(f"{WEATHER_BASE}/24hour").mock(
        return_value=httpx.Response(
            200,
            json={
                "list": [
                    {
                        "dateTime": "2026-04-30T18:00",
                        "values": {
                            "ttt": {"value": 14.0},
                            "rr": {"value": 0.0},
                            "weatherCode": {"value": 1},
                        },
                    }
                ]
            },
        )
    )
    epg_route = respx.get(f"{EPG_BASE}/programs").mock(
        return_value=httpx.Response(
            200,
            json={
                "programList": [
                    {
                        "startTime": "19:30",
                        "title": "Tagesschau",
                        "description": "Die Hauptausgabe der Nachrichten.",
                    }
                ]
            },
        )
    )

    result = await srgssr_daily_briefing(_briefing_input())

    assert "Tagesbriefing" in result
    assert "## Wetter (24h)" in result
    assert "14.0" in result
    assert "## TV-/Radioprogramm" in result
    assert "Tagesschau" in result
    assert weather_route.called
    assert epg_route.called


@respx.mock
async def test_daily_briefing_runs_upstreams_in_parallel():
    """asyncio.gather should kick off both calls before either resolves."""
    inflight = 0
    peak = 0

    async def _trace(request):
        nonlocal inflight, peak
        inflight += 1
        peak = max(peak, inflight)
        # yield to the event loop so the sibling coroutine gets a chance to start
        await asyncio.sleep(0)
        inflight -= 1
        if "/24hour" in str(request.url):
            return httpx.Response(200, json={"list": []})
        return httpx.Response(200, json={"programList": []})

    respx.get(f"{WEATHER_BASE}/24hour").mock(side_effect=_trace)
    respx.get(f"{EPG_BASE}/programs").mock(side_effect=_trace)

    await srgssr_daily_briefing(_briefing_input())

    assert peak == 2, f"expected concurrent fan-out (peak=2), saw peak={peak}"


@respx.mock
async def test_daily_briefing_partial_failure_renders_remaining_section():
    """When EPG returns 404 the weather section must still render (graceful degradation)."""
    respx.get(f"{WEATHER_BASE}/24hour").mock(
        return_value=httpx.Response(
            200,
            json={
                "list": [
                    {
                        "dateTime": "2026-04-30T12:00",
                        "values": {"ttt": {"value": 22.5}, "rr": {"value": 0.0}, "weatherCode": {"value": 2}},
                    }
                ]
            },
        )
    )
    respx.get(f"{EPG_BASE}/programs").mock(
        return_value=httpx.Response(404, text="Not Found")
    )

    result = await srgssr_daily_briefing(_briefing_input(channel_id="bogus"))

    # Weather rendered normally
    assert "22.5" in result
    # EPG section shows the 404 hint instead of programs
    assert "404" in result
    assert "srgssr_video_get_livestreams" in result


@respx.mock
async def test_daily_briefing_json_format_returns_both_payloads():
    respx.get(f"{WEATHER_BASE}/24hour").mock(
        return_value=httpx.Response(200, json={"list": [{"dateTime": "2026-04-30T00:00"}]})
    )
    respx.get(f"{EPG_BASE}/programs").mock(
        return_value=httpx.Response(
            200, json={"programList": [{"startTime": "08:00", "title": "Echo der Zeit"}]}
        )
    )

    result = await srgssr_daily_briefing(
        _briefing_input(response_format=ResponseFormat.JSON)
    )

    payload = json.loads(result)
    assert payload["channel_id"] == "srf1"
    assert payload["business_unit"] == "srf"
    assert payload["weather"]["list"][0]["dateTime"] == "2026-04-30T00:00"
    assert payload["epg"][0]["title"] == "Echo der Zeit"


# ---------------------------------------------------------------------------
# Settings / Inversion-of-Control (ARCH-004)
# ---------------------------------------------------------------------------

import pytest as _pytest  # noqa: E402

from srgssr_mcp import server as _server  # noqa: E402
from srgssr_mcp.server import Settings  # noqa: E402


def test_settings_reads_credentials_from_env(monkeypatch):
    monkeypatch.setenv("SRGSSR_CONSUMER_KEY", "env-key")
    monkeypatch.setenv("SRGSSR_CONSUMER_SECRET", "env-secret")
    monkeypatch.delenv("SRGSSR_MCP_TRANSPORT", raising=False)
    s = Settings()
    assert s.consumer_key.get_secret_value() == "env-key"
    assert s.consumer_secret.get_secret_value() == "env-secret"
    assert s.transport == "stdio"
    assert s.host == "127.0.0.1"
    assert s.port == 8000


def test_settings_transport_override(monkeypatch):
    monkeypatch.setenv("SRGSSR_MCP_TRANSPORT", "sse")
    monkeypatch.setenv("SRGSSR_MCP_HOST", "0.0.0.0")
    monkeypatch.setenv("SRGSSR_MCP_PORT", "9001")
    s = Settings()
    assert s.transport == "sse"
    assert s.host == "0.0.0.0"
    assert s.port == 9001


def test_settings_rejects_invalid_transport(monkeypatch):
    monkeypatch.setenv("SRGSSR_MCP_TRANSPORT", "carrier-pigeon")
    with _pytest.raises(Exception):
        Settings()


def test_require_credentials_raises_when_missing(monkeypatch):
    monkeypatch.delenv("SRGSSR_CONSUMER_KEY", raising=False)
    monkeypatch.delenv("SRGSSR_CONSUMER_SECRET", raising=False)
    # _env_file=None disables .env auto-loading, so a local/CI workspace with
    # a populated .env cannot make this test pass nondeterministically.
    s = Settings(_env_file=None)
    with _pytest.raises(ValueError, match="SRGSSR_CONSUMER_KEY"):
        s.require_credentials()


def test_secrets_not_leaked_in_repr(monkeypatch):
    """SecretStr must mask the value in repr/str/dict to prevent log leaks."""
    monkeypatch.setenv("SRGSSR_CONSUMER_KEY", "super-key-12345")
    monkeypatch.setenv("SRGSSR_CONSUMER_SECRET", "super-secret-67890")
    s = Settings(_env_file=None)
    rendered = repr(s)
    assert "super-key-12345" not in rendered
    assert "super-secret-67890" not in rendered
    # Plain str of SecretStr also masks
    assert "super-key-12345" not in str(s.consumer_key)
    assert "super-secret-67890" not in str(s.consumer_secret)
    # But require_credentials() still returns the cleartext for actual use
    key, secret = s.require_credentials()
    assert key == "super-key-12345"
    assert secret == "super-secret-67890"


def test_get_credentials_uses_settings(monkeypatch):
    monkeypatch.setenv("SRGSSR_CONSUMER_KEY", "via-settings")
    monkeypatch.setenv("SRGSSR_CONSUMER_SECRET", "shh")
    _server.get_settings.cache_clear()
    try:
        assert _server._get_credentials() == ("via-settings", "shh")
    finally:
        _server.get_settings.cache_clear()


def test_settings_cache_refreshes_after_ttl(monkeypatch):
    """SEC-013: rotated env credentials are picked up after SETTINGS_TTL_SECONDS."""
    from srgssr_mcp import config as _config

    monkeypatch.setenv("SRGSSR_CONSUMER_KEY", "key-v1")
    monkeypatch.setenv("SRGSSR_CONSUMER_SECRET", "secret-v1")
    _config.get_settings.cache_clear()

    s1 = _config.get_settings()
    assert s1.consumer_key == "key-v1"

    # Rotate creds in the env, but stay within the TTL window — cache holds.
    monkeypatch.setenv("SRGSSR_CONSUMER_KEY", "key-v2")
    s2 = _config.get_settings()
    assert s2.consumer_key == "key-v1", "cache should still be warm before TTL elapses"

    # Simulate TTL elapse: directly age the cache entry.
    _config._settings_cache["loaded_at"] -= _config.SETTINGS_TTL_SECONDS + 1.0
    s3 = _config.get_settings()
    assert s3.consumer_key == "key-v2", "cache must refresh after TTL elapses"

    _config.get_settings.cache_clear()


def test_build_mcp_applies_host_port(monkeypatch):
    monkeypatch.setenv("SRGSSR_MCP_HOST", "10.0.0.5")
    monkeypatch.setenv("SRGSSR_MCP_PORT", "7777")
    monkeypatch.setenv("SRGSSR_MCP_MOUNT_PATH", "/srg")
    _server.get_settings.cache_clear()
    try:
        s = _server.get_settings()
        original_host = mcp.settings.host
        original_port = mcp.settings.port
        original_mount = mcp.settings.mount_path
        try:
            built = _server._build_mcp(s)
            assert built is mcp
            assert built.settings.host == "10.0.0.5"
            assert built.settings.port == 7777
            assert built.settings.mount_path == "/srg"
        finally:
            mcp.settings.host = original_host
            mcp.settings.port = original_port
            mcp.settings.mount_path = original_mount
    finally:
        _server.get_settings.cache_clear()


def test_main_dispatches_to_configured_transport(monkeypatch):
    monkeypatch.setenv("SRGSSR_CONSUMER_KEY", "k")
    monkeypatch.setenv("SRGSSR_CONSUMER_SECRET", "s")
    monkeypatch.setenv("SRGSSR_MCP_TRANSPORT", "streamable-http")
    monkeypatch.delenv("SRGSSR_MCP_MOUNT_PATH", raising=False)
    _server.get_settings.cache_clear()

    calls: list[dict] = []

    def _fake_run(self, transport="stdio", mount_path=None):
        calls.append({"transport": transport, "mount_path": mount_path})

    monkeypatch.setattr(type(mcp), "run", _fake_run)
    try:
        _server.main()
    finally:
        _server.get_settings.cache_clear()

    assert calls == [{"transport": "streamable-http", "mount_path": None}]


def test_main_defaults_to_stdio(monkeypatch):
    monkeypatch.setenv("SRGSSR_CONSUMER_KEY", "k")
    monkeypatch.setenv("SRGSSR_CONSUMER_SECRET", "s")
    monkeypatch.delenv("SRGSSR_MCP_TRANSPORT", raising=False)
    _server.get_settings.cache_clear()

    calls: list[dict] = []

    def _fake_run(self, transport="stdio", mount_path=None):
        calls.append({"transport": transport, "mount_path": mount_path})

    monkeypatch.setattr(type(mcp), "run", _fake_run)
    try:
        _server.main()
    finally:
        _server.get_settings.cache_clear()

    assert calls == [{"transport": "stdio", "mount_path": None}]


# ---------------------------------------------------------------------------
# MCP Primitives: Resources & Prompts (ARCH-008)
# ---------------------------------------------------------------------------


async def test_resource_templates_registered():
    templates = await mcp.list_resource_templates()
    uris = {t.uriTemplate for t in templates}
    assert "epg://{bu}/{channel_id}/{date}" in uris
    assert "votation://{votation_id}" in uris


async def test_prompts_registered():
    prompts = await mcp.list_prompts()
    names = {p.name for p in prompts}
    assert "analyse_abstimmungsverhalten" in names
    assert "tagesbriefing_kanton" in names


@respx.mock
async def test_epg_resource_returns_markdown():
    respx.get(f"{EPG_BASE}/programs").mock(
        return_value=httpx.Response(
            200,
            json={
                "programList": [
                    {
                        "startTime": "20:00",
                        "title": "Tagesschau",
                        "subtitle": "Hauptausgabe",
                        "description": "Nachrichten",
                    }
                ]
            },
        )
    )
    contents = list(await mcp.read_resource("epg://srf/srf1/2026-04-30"))
    assert len(contents) == 1
    body = contents[0].content
    assert "Programm" in body
    assert "SRF1" in body
    assert "Tagesschau" in body
    assert "2026-04-30" in body


async def test_epg_resource_rejects_unsupported_business_unit():
    contents = list(await mcp.read_resource("epg://rtr/rtr1/2026-04-30"))
    body = contents[0].content
    assert "EPG nicht verfügbar" in body
    assert "rtr" in body.lower()


@respx.mock
async def test_epg_resource_handles_404():
    respx.get(f"{EPG_BASE}/programs").mock(
        return_value=httpx.Response(404, text="not found")
    )
    contents = list(await mcp.read_resource("epg://srf/unknown/2026-04-30"))
    body = contents[0].content
    assert "404" in body
    assert "srgssr_video_get_livestreams" in body


@respx.mock
async def test_votation_resource_returns_markdown():
    respx.get(f"{POLIS_BASE}/votations/v1").mock(
        return_value=httpx.Response(
            200,
            json={
                "title": "Maskeninitiative",
                "date": "2024-09-22",
                "result": {
                    "yesPercentage": 53.4,
                    "noPercentage": 46.6,
                    "accepted": True,
                    "turnout": 47.1,
                },
                "cantonalResults": [
                    {"canton": "ZH", "yesPercentage": 55.0, "accepted": True},
                ],
            },
        )
    )
    contents = list(await mcp.read_resource("votation://v1"))
    body = contents[0].content
    assert "Maskeninitiative" in body
    assert "Angenommen" in body
    assert "53.4" in body
    assert "ZH" in body


@respx.mock
async def test_votation_resource_handles_404():
    respx.get(f"{POLIS_BASE}/votations/missing").mock(
        return_value=httpx.Response(404, text="not found")
    )
    contents = list(await mcp.read_resource("votation://missing"))
    body = contents[0].content
    assert "404" in body
    assert "srgssr_polis_get_votations" in body


async def test_analyse_abstimmungsverhalten_prompt_default_focus():
    result = await mcp.get_prompt(
        "analyse_abstimmungsverhalten", {"votation_id": "v123"}
    )
    text = result.messages[0].content.text
    assert "v123" in text
    assert "Stadt-Land" in text
    assert "votation://v123" in text


async def test_analyse_abstimmungsverhalten_prompt_focus_kantone():
    result = await mcp.get_prompt(
        "analyse_abstimmungsverhalten",
        {"votation_id": "v999", "focus": "kantone"},
    )
    text = result.messages[0].content.text
    assert "v999" in text
    assert "kantonale Ausreisser" in text


async def test_tagesbriefing_kanton_prompt_default():
    result = await mcp.get_prompt(
        "tagesbriefing_kanton", {"location": "Zürich"}
    )
    text = result.messages[0].content.text
    assert "Zürich" in text
    assert "srgssr_daily_briefing" in text
    assert "epg://srf/srf1" in text
    assert "heutige Datum" in text


async def test_tagesbriefing_kanton_prompt_with_date_and_channel():
    result = await mcp.get_prompt(
        "tagesbriefing_kanton",
        {
            "location": "Lausanne",
            "channel_id": "rts1",
            "business_unit": "rts",
            "date": "2026-05-01",
        },
    )
    text = result.messages[0].content.text
    assert "Lausanne" in text
    assert "rts1" in text
    assert "epg://rts/rts1" in text
    assert "2026-05-01" in text


# ---------------------------------------------------------------------------
# HTTP plumbing: OAuth token refresh + error mapping (OPS-001 coverage gap)
# ---------------------------------------------------------------------------


@respx.mock
async def test_oauth_token_cache_hit_skips_refresh():
    """A non-expired cached token short-circuits the OAuth round-trip."""
    token_route = respx.post(_server.TOKEN_URL).mock(
        return_value=httpx.Response(500, json={"error": "should_not_be_called"})
    )
    cleared = await _server._get_access_token()
    assert cleared == "test-token"
    assert not token_route.called


@respx.mock
async def test_oauth_token_refresh_posts_to_token_url(monkeypatch):
    """When the cache is cold, the helper acquires a new token and caches it."""
    monkeypatch.setenv("SRGSSR_CONSUMER_KEY", "k")
    monkeypatch.setenv("SRGSSR_CONSUMER_SECRET", "s")
    _server.get_settings.cache_clear()
    _server._token_cache["access_token"] = None
    _server._token_cache["expires_at"] = 0.0

    token_route = respx.post(_server.TOKEN_URL).mock(
        return_value=httpx.Response(
            200, json={"access_token": "fresh-token", "expires_in": 1800}
        )
    )
    try:
        token = await _server._get_access_token()
    finally:
        _server.get_settings.cache_clear()

    assert token == "fresh-token"
    assert token_route.called
    request = token_route.calls.last.request
    # Basic auth header carries base64(key:secret)
    assert request.headers["Authorization"].startswith("Basic ")
    assert _server._token_cache["access_token"] == "fresh-token"
    assert _server._token_cache["expires_at"] > 0


def test_handle_error_value_error_returns_config_message():
    msg = _server._handle_error(ValueError("SRGSSR_CONSUMER_KEY missing"))
    assert msg.startswith("Konfigurationsfehler")
    assert "SRGSSR_CONSUMER_KEY" in msg


def test_handle_error_timeout_returns_localized_message():
    msg = _server._handle_error(httpx.TimeoutException("read timed out"))
    assert "Timeout" in msg


def test_handle_error_unknown_exception_returns_unexpected_message():
    msg = _server._handle_error(RuntimeError("kaboom"))
    assert msg.startswith("Unerwarteter Fehler")
    assert "RuntimeError" in msg  # exception type is allowed (helpful, no internals)
    # OBS-002: internal exception message must not reach the user
    assert "kaboom" not in msg


def test_handle_error_default_does_not_leak_socket_internals():
    """OBS-002: a gaierror like 'getaddrinfo: nodename nor servname provided'
    must not surface in the tool result, only in the structured log."""
    import socket as _stdlib_socket

    err = _stdlib_socket.gaierror("getaddrinfo failed for host secret-internal.local")
    msg = _server._handle_error(err)
    assert "secret-internal.local" not in msg
    assert "getaddrinfo failed" not in msg
    assert "gaierror" in msg  # exception type is OK, internal details are not


def test_handle_error_status_500_includes_truncated_body():
    response = httpx.Response(500, text="x" * 500, request=httpx.Request("GET", "http://x"))
    msg = _server._handle_error(httpx.HTTPStatusError("500", request=response.request, response=response))
    assert msg.startswith("API-Fehler 500")
    # body is truncated to 200 chars
    assert msg.count("x") <= 200


def test_handle_error_404_with_hint_appends_recovery_tip():
    response = httpx.Response(404, request=httpx.Request("GET", "http://x"))
    msg = _server._handle_error(
        httpx.HTTPStatusError("404", request=response.request, response=response),
        not_found_hint="Try a different ID.",
    )
    assert "404" in msg
    assert "Try a different ID." in msg


# ---------------------------------------------------------------------------
# SSRF defense: HTTPS enforcement + host allowlist + IP blocklist (SEC-004)
# ---------------------------------------------------------------------------

import socket as _socket  # noqa: E402
from urllib.parse import urlparse  # noqa: E402

from srgssr_mcp import _http as _http_mod  # noqa: E402


def _fake_addrinfo(ip: str):
    """Build an addrinfo-shaped tuple list for a single IP, IPv4 or IPv6."""
    family = _socket.AF_INET6 if ":" in ip else _socket.AF_INET
    sockaddr = (ip, 0, 0, 0) if family == _socket.AF_INET6 else (ip, 0)
    return [(family, _socket.SOCK_STREAM, 6, "", sockaddr)]


def test_validate_url_safe_rejects_http_scheme():
    with _pytest.raises(ValueError, match="HTTPS"):
        _server._validate_url_safe("http://api.srgssr.ch/foo")


def test_validate_url_safe_rejects_file_scheme():
    with _pytest.raises(ValueError, match="SSRF blocked"):
        _server._validate_url_safe("file:///etc/passwd")


def test_validate_url_safe_rejects_ftp_scheme():
    with _pytest.raises(ValueError, match="SSRF blocked"):
        _server._validate_url_safe("ftp://api.srgssr.ch/foo")


def test_validate_url_safe_rejects_url_without_hostname():
    with _pytest.raises(ValueError, match="no hostname"):
        _server._validate_url_safe("https:///path-only")


def test_validate_url_safe_rejects_host_outside_allowlist():
    with _pytest.raises(ValueError, match="egress allowlist"):
        _server._validate_url_safe("https://evil.example.com/foo")


def test_validate_url_safe_rejects_attacker_controlled_subdomain():
    # Subtle SSRF attempt: looks similar to the allowed host but differs.
    with _pytest.raises(ValueError, match="egress allowlist"):
        _server._validate_url_safe("https://api.srgssr.ch.evil.example/foo")


def test_validate_url_safe_rejects_private_rfc1918_ip(monkeypatch):
    monkeypatch.setattr(
        _http_mod.socket, "getaddrinfo", lambda *a, **kw: _fake_addrinfo("192.168.1.1")
    )
    with _pytest.raises(ValueError, match="192.168.1.1"):
        _server._validate_url_safe("https://api.srgssr.ch/foo")


def test_validate_url_safe_rejects_loopback_ip(monkeypatch):
    monkeypatch.setattr(
        _http_mod.socket, "getaddrinfo", lambda *a, **kw: _fake_addrinfo("127.0.0.1")
    )
    with _pytest.raises(ValueError, match="127.0.0.1"):
        _server._validate_url_safe("https://api.srgssr.ch/foo")


def test_validate_url_safe_rejects_aws_metadata_link_local(monkeypatch):
    # 169.254.169.254 is the cloud-metadata IP — the canonical SSRF target.
    monkeypatch.setattr(
        _http_mod.socket,
        "getaddrinfo",
        lambda *a, **kw: _fake_addrinfo("169.254.169.254"),
    )
    with _pytest.raises(ValueError, match="169.254.169.254"):
        _server._validate_url_safe("https://api.srgssr.ch/foo")


def test_validate_url_safe_rejects_ipv6_loopback(monkeypatch):
    monkeypatch.setattr(
        _http_mod.socket, "getaddrinfo", lambda *a, **kw: _fake_addrinfo("::1")
    )
    with _pytest.raises(ValueError, match="blocked range"):
        _server._validate_url_safe("https://api.srgssr.ch/foo")


def test_validate_url_safe_rejects_ipv6_unique_local(monkeypatch):
    monkeypatch.setattr(
        _http_mod.socket, "getaddrinfo", lambda *a, **kw: _fake_addrinfo("fc00::1")
    )
    with _pytest.raises(ValueError, match="blocked range"):
        _server._validate_url_safe("https://api.srgssr.ch/foo")


def test_validate_url_safe_rejects_dns_failure(monkeypatch):
    def _boom(*_a, **_kw):
        raise _socket.gaierror("temporary failure in name resolution")

    monkeypatch.setattr(_http_mod.socket, "getaddrinfo", _boom)
    with _pytest.raises(ValueError, match="cannot resolve"):
        _server._validate_url_safe("https://api.srgssr.ch/foo")


def test_validate_url_safe_rejects_when_any_resolved_ip_is_blocked(monkeypatch):
    # An attacker who controls DNS could rebind a hostname to multiple IPs:
    # one public, one private. We must reject the whole hostname.
    mixed = [
        (_socket.AF_INET, _socket.SOCK_STREAM, 6, "", ("8.8.8.8", 0)),
        (_socket.AF_INET, _socket.SOCK_STREAM, 6, "", ("10.0.0.1", 0)),
    ]
    monkeypatch.setattr(_http_mod.socket, "getaddrinfo", lambda *a, **kw: mixed)
    with _pytest.raises(ValueError, match="10.0.0.1"):
        _server._validate_url_safe("https://api.srgssr.ch/foo")


def test_validate_url_safe_accepts_public_srgssr_host(monkeypatch):
    monkeypatch.setattr(
        _http_mod.socket, "getaddrinfo", lambda *a, **kw: _fake_addrinfo("63.178.6.210")
    )
    # No exception means the URL passed all three controls.
    _server._validate_url_safe("https://api.srgssr.ch/forecasts/v2.0/weather/current")


async def test_api_get_blocks_non_https_url():
    with _pytest.raises(ValueError, match="HTTPS"):
        await _server._api_get("http://api.srgssr.ch/foo")


async def test_api_get_blocks_disallowed_host():
    with _pytest.raises(ValueError, match="egress allowlist"):
        await _server._api_get("https://attacker.example.com/exfil")


async def test_safe_api_get_returns_localized_message_on_ssrf_block():
    """SSRF rejections surface as `Konfigurationsfehler` via _handle_error."""
    msg = await _server._safe_api_get("http://api.srgssr.ch/foo")
    assert isinstance(msg, str)
    assert msg.startswith("Konfigurationsfehler")
    assert "SSRF" in msg or "HTTPS" in msg


def test_handle_error_maps_ssrf_value_error_to_config_message():
    msg = _server._handle_error(ValueError("SSRF blocked: only HTTPS is permitted"))
    assert msg.startswith("Konfigurationsfehler")
    assert "SSRF" in msg


def test_token_url_is_https_and_in_allowlist():
    # The hard-coded TOKEN_URL must itself satisfy the SSRF policy.
    parsed = urlparse(_server.TOKEN_URL)
    assert parsed.scheme == "https"
    assert parsed.hostname in _server.ALLOWED_HOSTS


def test_all_base_urls_are_https_and_in_allowlist():
    for base in (
        _server.BASE_URL,
        _server.WEATHER_BASE,
        _server.VIDEO_BASE,
        _server.AUDIO_BASE,
        _server.EPG_BASE,
        _server.POLIS_BASE,
        _server.TOKEN_URL,
    ):
        parsed = urlparse(base)
        assert parsed.scheme == "https", f"{base} must use HTTPS"
        assert parsed.hostname in _server.ALLOWED_HOSTS, (
            f"{base} hostname must be in ALLOWED_HOSTS"
        )


# ---------------------------------------------------------------------------
# SEC-018: Input validation hardening (Pydantic strict + extra=forbid + patterns)
# ---------------------------------------------------------------------------

from pydantic import ValidationError as _ValidationError  # noqa: E402

_TOOL_INPUT_MODELS = (
    EpgProgramsInput,
    AudioEpisodesInput,
    PolisListInput,
    PolisResultInput,
    VideoShowsInput,
    VideoEpisodesInput,
    VideoLivestreamsInput,
    WeatherSearchInput,
    WeatherForecastInput,
    DailyBriefingInput,
)


def test_all_tool_inputs_enforce_strict_mode():
    """Every tool input model must run Pydantic in strict mode (SEC-018)."""
    for model in _TOOL_INPUT_MODELS:
        cfg = model.model_config
        assert cfg.get("strict") is True, (
            f"{model.__name__} model_config must set strict=True"
        )


def test_all_tool_inputs_forbid_extra_fields():
    """Every tool input model must reject unknown fields (SEC-018)."""
    for model in _TOOL_INPUT_MODELS:
        cfg = model.model_config
        assert cfg.get("extra") == "forbid", (
            f"{model.__name__} model_config must set extra='forbid'"
        )


def test_strict_mode_rejects_string_for_int_field():
    """Strict mode must refuse implicit str→int coercion."""
    with pytest.raises(_ValidationError):
        VideoShowsInput(business_unit=BusinessUnit.SRF, page_size="20")  # type: ignore[arg-type]


def test_strict_mode_rejects_string_for_float_field():
    """Strict mode must refuse implicit str→float coercion."""
    with pytest.raises(_ValidationError):
        WeatherForecastInput(latitude="47.0", longitude=8.0)  # type: ignore[arg-type]


def test_extra_field_rejected_on_video_shows_input():
    with pytest.raises(_ValidationError):
        VideoShowsInput(business_unit=BusinessUnit.SRF, unknown_param="x")  # type: ignore[call-arg]


def test_extra_field_rejected_on_weather_forecast_input():
    with pytest.raises(_ValidationError):
        WeatherForecastInput(  # type: ignore[call-arg]
            latitude=47.0,
            longitude=8.0,
            sneaky="injected",
        )


def test_epg_channel_id_rejects_path_traversal():
    """Patterns must block path-traversal-style payloads in IDs."""
    with pytest.raises(_ValidationError):
        EpgProgramsInput(
            business_unit=BusinessUnit.SRF,
            channel_id="../../etc/passwd",
            date="2026-04-30",
        )


def test_epg_channel_id_rejects_url_injection():
    with pytest.raises(_ValidationError):
        EpgProgramsInput(
            business_unit=BusinessUnit.SRF,
            channel_id="srf1?evil=1",
            date="2026-04-30",
        )


def test_video_show_id_rejects_whitespace_injection():
    with pytest.raises(_ValidationError):
        VideoEpisodesInput(business_unit=BusinessUnit.SRF, show_id="srf tagesschau")


def test_audio_show_id_rejects_slash():
    with pytest.raises(_ValidationError):
        AudioEpisodesInput(business_unit=BusinessUnit.SRF, show_id="echo/../foo")


def test_polis_votation_id_rejects_special_chars():
    with pytest.raises(_ValidationError):
        PolisResultInput(votation_id="v1; DROP TABLE")


def test_polis_canton_rejects_digits():
    with pytest.raises(_ValidationError):
        PolisListInput(canton="Z1")


def test_polis_canton_rejects_too_short():
    with pytest.raises(_ValidationError):
        PolisListInput(canton="Z")


def test_polis_canton_accepts_valid_two_letter():
    # Sanity: legitimate kantonal cases still pass.
    p = PolisListInput(canton="zh")
    assert p.canton == "zh"


def test_weather_query_rejects_html_payload():
    with pytest.raises(_ValidationError):
        WeatherSearchInput(query="<script>alert(1)</script>")


def test_weather_query_accepts_unicode_city_name():
    # Unicode word characters (umlauts, accents) must still pass.
    assert WeatherSearchInput(query="Zürich").query == "Zürich"
    assert WeatherSearchInput(query="Genève").query == "Genève"
    assert WeatherSearchInput(query="8001").query == "8001"


def test_weather_geolocation_id_rejects_special_chars():
    with pytest.raises(_ValidationError):
        WeatherForecastInput(
            latitude=47.0, longitude=8.0, geolocation_id="100123;rm -rf"
        )


def test_weather_latitude_out_of_range_rejected():
    with pytest.raises(_ValidationError):
        WeatherForecastInput(latitude=10.0, longitude=8.0)


def test_video_page_size_zero_rejected():
    with pytest.raises(_ValidationError):
        VideoShowsInput(business_unit=BusinessUnit.SRF, page_size=0)


def test_video_page_size_above_limit_rejected():
    with pytest.raises(_ValidationError):
        VideoShowsInput(business_unit=BusinessUnit.SRF, page_size=101)


def test_polis_year_out_of_range_rejected():
    with pytest.raises(_ValidationError):
        PolisListInput(year_from=1800)


def test_daily_briefing_channel_id_rejects_special_chars():
    with pytest.raises(_ValidationError):
        DailyBriefingInput(
            business_unit=BusinessUnit.SRF,
            channel_id="srf1 OR 1=1",
            date="2026-04-30",
            latitude=47.0,
            longitude=8.0,
        )


def test_daily_briefing_extra_field_rejected():
    with pytest.raises(_ValidationError):
        DailyBriefingInput(  # type: ignore[call-arg]
            business_unit=BusinessUnit.SRF,
            channel_id="srf1",
            date="2026-04-30",
            latitude=47.0,
            longitude=8.0,
            extra_payload="x",
        )
