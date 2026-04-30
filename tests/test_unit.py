"""Unit tests with mocked HTTP responses (fast, CI-safe).

Each tool covers three scenarios:
1. Happy path  — 200 with realistic payload, markdown rendering checked
2. Error path  — 4xx/5xx, tool returns localized error string instead of raising
3. Edge case   — empty list / JSON format / boundary input

Tools are called directly (the @mcp.tool decorator does not wrap them);
input is constructed via the Pydantic models from server.py.
"""
import httpx
import pytest
import respx

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
    mcp,
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
    assert s.consumer_key == "env-key"
    assert s.consumer_secret == "env-secret"
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


def test_require_credentials_raises_when_missing():
    s = Settings(consumer_key="", consumer_secret="")
    with _pytest.raises(ValueError, match="SRGSSR_CONSUMER_KEY"):
        s.require_credentials()


def test_get_credentials_uses_settings(monkeypatch):
    monkeypatch.setenv("SRGSSR_CONSUMER_KEY", "via-settings")
    monkeypatch.setenv("SRGSSR_CONSUMER_SECRET", "shh")
    _server.get_settings.cache_clear()
    try:
        assert _server._get_credentials() == ("via-settings", "shh")
    finally:
        _server.get_settings.cache_clear()


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
