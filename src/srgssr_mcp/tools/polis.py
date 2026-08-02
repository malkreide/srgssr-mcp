"""Polis tools: Swiss votations, votation results, and elections (since 1900).

The v2 API does not filter by year or canton. It keys off `caseid` (a voting
day, from /cases) and `locationid` (from /locations), so the year and canton
arguments this module exposes are resolved into those before the request goes
out. Doing that here rather than dropping the arguments keeps the tools able to
answer the questions people actually ask — "votes in Bern between 2010 and
2020" — instead of quietly returning everything.
"""

import asyncio
import re
import time
from datetime import datetime, timezone

from mcp.server.mcpserver import Context
from pydantic import BaseModel, ConfigDict, Field

from srgssr_mcp._app import mcp
from srgssr_mcp._http import POLIS_BASE, _api_get, _build_error_response
from srgssr_mcp._models import (
    Election,
    ElectionsResponse,
    ToolErrorResponse,
    Votation,
    VotationResultResponse,
    VotationsResponse,
)
from srgssr_mcp.logging_config import get_logger

logger = get_logger("mcp.srgssr.polis")

# Polis reaches back to 1900; anything outside this window is a misread date
# rather than a real one.
_PLAUSIBLE_YEARS = (1800, 2100)

# locationtypeid 2 is "Canton (Kanton)" per the API's own enumeration.
_LOCATIONTYPE_CANTON = 2

# The API's location records carry names, not abbreviations, so the standard
# two-letter codes are mapped here. They are fixed by the federal constitution
# and have not changed since 1979 — reference data, not a guess.
_CANTON_NAMES: dict[str, str] = {
    "ZH": "zürich",
    "BE": "bern",
    "LU": "luzern",
    "UR": "uri",
    "SZ": "schwyz",
    "OW": "obwalden",
    "NW": "nidwalden",
    "GL": "glarus",
    "ZG": "zug",
    "FR": "freiburg",
    "SO": "solothurn",
    "BS": "basel-stadt",
    "BL": "basel-landschaft",
    "SH": "schaffhausen",
    "AR": "appenzell ausserrhoden",
    "AI": "appenzell innerrhoden",
    "SG": "st. gallen",
    "GR": "graubünden",
    "AG": "aargau",
    "TG": "thurgau",
    "TI": "tessin",
    "VD": "waadt",
    "VS": "wallis",
    "NE": "neuenburg",
    "GE": "genf",
    "JU": "jura",
}

# /cases?listAllCases=true is documented as slow and "should not be done more
# than once a day", and the canton list changes about as often as Swiss cantons
# do. Both are cached process-wide with a generous TTL rather than fetched per
# call.
_REFERENCE_TTL_SECONDS = 6 * 3600
_reference_cache: dict[str, dict] = {}


def _cached(key: str):
    entry = _reference_cache.get(key)
    if entry and (time.monotonic() - entry["at"]) < _REFERENCE_TTL_SECONDS:
        return entry["value"]
    return None


def _cache(key: str, value):
    _reference_cache[key] = {"value": value, "at": time.monotonic()}
    return value


def _clear_reference_cache() -> None:
    """Drop cached locations and cases. Test-only helper."""
    _reference_cache.clear()


def _as_items(data, *path: str) -> list:
    """Walk a Polis payload down to its list.

    The OpenAPI spec leaves the 200 responses undocumented (``content: {}``),
    so these container names come from live responses measured 2026-07-31.
    They are XML-derived and PascalCase, and they are not uniform: votations
    sit in a top-level ``Items`` array, cases in ``Case``, but elections are
    one level deeper under ``Elections.Election`` — a dict wrapping the array,
    which is why an explicit path beats guessing at the first list found.
    """
    node = data
    for key in path:
        if isinstance(node, dict):
            node = node.get(key)
        else:
            return []
    if isinstance(node, list):
        return node
    # A single-element response is delivered unwrapped rather than as a
    # one-item array.
    return [node] if isinstance(node, dict) else []


def _year_of(entry: dict) -> int | None:
    """Year of a case or votation, or None if the date cannot be read.

    ``EventDate`` is the field, but the service is .NET-XML-derived — the
    payload uses PascalCase and ``*Specified`` companion flags — so the value
    arrives either as an ISO string or in the ``/Date(1601164800000)/``
    epoch-milliseconds form. Both are handled.

    The result is checked against a plausible range. Grabbing the first four
    digits of an epoch timestamp yields 1601, which silently passed every
    year filter and made a full result set look like an empty period.
    """
    raw = _text(entry.get("EventDate")) or _text(entry.get("date"))
    if not raw:
        return None

    epoch = re.search(r"/Date\((-?\d+)", raw)
    if epoch:
        try:
            year = datetime.fromtimestamp(int(epoch.group(1)) / 1000, tz=timezone.utc).year
        except (ValueError, OSError, OverflowError):
            return None
        return year if _PLAUSIBLE_YEARS[0] <= year <= _PLAUSIBLE_YEARS[1] else None

    for candidate in re.findall(r"\d{4}", raw):
        year = int(candidate)
        if _PLAUSIBLE_YEARS[0] <= year <= _PLAUSIBLE_YEARS[1]:
            return year
    return None


def _decorate(payload, items: list) -> list:
    """Attach the payload's ``Case`` to each item.

    Elections have no title or date of their own — those live on the sibling
    ``Case`` object — so the pairing has to survive the flattening.
    """
    case = payload.get("Case") if isinstance(payload, dict) else None
    if isinstance(case, list):
        case = case[0] if case else None
    if not isinstance(case, dict):
        return items
    return [{**item, "_case": case} for item in items]


async def _fetch_filtered(endpoint: str, container: tuple[str, ...], params: "PolisListInput") -> list:
    """Fetch votations or elections, resolving year and canton into API filters.

    Without a year range this is one request. With one it is one request per
    voting day in that range, bounded by how many results the caller asked for
    — /votations accepts a single caseid, so there is no way to express a range
    in one call.
    """
    query: dict = {"lang": "de"}
    if params.canton:
        location_id = await _canton_location_id(params.canton)
        if location_id is None:
            raise ValueError(
                f"Kanton '{params.canton.upper()}' nicht gefunden. Erlaubt sind "
                f"die 26 Kantonskürzel, z.B. 'ZH', 'BE', 'TI'."
            )
        query["locationid"] = location_id

    if params.year_from is None and params.year_to is None:
        data = await _api_get(f"{POLIS_BASE}/{endpoint}", params=query)
        return _decorate(data, _as_items(data, *container))

    case_ids = await _case_ids_in_range(params.year_from, params.year_to)
    if not case_ids:
        return []
    # Enough voting days to fill the requested window, not the whole range.
    wanted = params.page * params.page_size
    results: list = []
    for chunk_start in range(0, len(case_ids), 5):
        chunk = case_ids[chunk_start : chunk_start + 5]
        payloads = await asyncio.gather(
            *(_api_get(f"{POLIS_BASE}/{endpoint}", params={**query, "caseid": cid}) for cid in chunk),
            return_exceptions=True,
        )
        for payload in payloads:
            if isinstance(payload, BaseException):
                logger.warning("case_fetch_failed", error_type=type(payload).__name__)
                continue
            results.extend(_decorate(payload, _as_items(payload, *container)))
        if len(results) >= wanted:
            break
    return results


async def _canton_location_id(canton: str) -> int | None:
    """Resolve a canton abbreviation to the locationid the API filters on."""
    cached = _cached("cantons")
    if cached is None:
        data = await _api_get(
            f"{POLIS_BASE}/locations",
            params={"locationtypeid": _LOCATIONTYPE_CANTON, "lang": "de"},
        )
        cached = _cache("cantons", _as_items(data, "Location"))
    code = canton.upper()
    expected_name = _CANTON_NAMES.get(code)
    for location in cached:
        names = {(_text(location.get(field)) or "").strip().lower() for field in ("LocationName", "Name", "Title")}
        names.discard("")
        if code.lower() in names or (expected_name and any(expected_name in name for name in names)):
            for id_field in ("id", "LocationID", "ID"):
                try:
                    return int(location[id_field])
                except (KeyError, TypeError, ValueError):
                    continue
    return None


async def _case_ids_in_range(year_from: int | None, year_to: int | None) -> list[int]:
    """Voting days inside the year range, newest first.

    /votations takes a single caseid, so a year range becomes one request per
    voting day. The list is bounded by the caller so a wide range does not turn
    into a hundred requests.
    """
    cached = _cached("cases")
    if cached is None:
        data = await _api_get(f"{POLIS_BASE}/cases", params={"lang": "de", "listAllCases": "true"})
        cached = _cache("cases", _as_items(data, "Case"))

    selected: list[tuple[int, str]] = []
    parsed_any = False
    for case in cached:
        year = _year_of(case)
        if year is None:
            continue
        parsed_any = True
        if year_from is not None and year < year_from:
            continue
        if year_to is not None and year > year_to:
            continue
        # The API wants an integer, but the id travels as a query parameter —
        # forcing int() here only risks discarding a usable value.
        case_id = case.get("id")
        if case_id is not None:
            selected.append((year, str(case_id)))

    if cached and not parsed_any:
        # Cases came back but not one date could be read. That is a parsing
        # fault, not an empty period, and returning [] would report it as
        # "no votations in that range".
        logger.error(
            "case_dates_unparseable",
            case_count=len(cached),
            sample_keys=sorted(cached[0])[:15],
        )
        raise ValueError(
            "Die Abstimmungstage von Polis liessen sich nicht auswerten — das "
            "Datumsfeld hat ein unerwartetes Format. Ohne Jahresfilter abfragen; "
            "die Feldnamen stehen im Server-Log unter 'case_dates_unparseable'."
        )

    selected.sort(reverse=True)
    return [case_id for _, case_id in selected]


class PolisListInput(BaseModel):
    model_config = ConfigDict(strict=True, str_strip_whitespace=True, extra="forbid")
    year_from: int | None = Field(default=None, ge=1900, le=2100)
    year_to: int | None = Field(default=None, ge=1900, le=2100)
    canton: str | None = Field(default=None, min_length=2, max_length=4, pattern=r"^[A-Za-z]{2,4}$")
    page_size: int | None = Field(default=20, ge=1, le=100)
    page: int | None = Field(default=1, ge=1)


class PolisResultInput(BaseModel):
    model_config = ConfigDict(strict=True, str_strip_whitespace=True, extra="forbid")
    votation_id: str = Field(..., min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")


def _text(value) -> str | None:
    """Flatten a Polis text field.

    Titles arrive either as a plain string or as the XML-derived
    ``{"Text": [...]}``/list form, depending on the endpoint.
    """
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, list):
        parts = [_text(v) for v in value]
        joined = " ".join(p for p in parts if p)
        return joined or None
    if isinstance(value, dict):
        for key in ("Text", "#text", "value", "Name"):
            if key in value:
                return _text(value[key])
    return None


def _votation_from_dict(d: dict) -> Votation:
    return Votation(
        id=str(d.get("id", "?")),
        date=d.get("EventDate") or d.get("date"),
        title=_text(d.get("Title")),
    )


def _election_from_dict(d: dict, case: dict | None = None) -> Election:
    """Elections carry no title or date of their own.

    The payload puts them under ``Elections.Election`` next to a single
    ``Case`` object that holds the voting day's title and date, so that is
    where those two come from.
    """
    case = case or {}
    return Election(
        id=str(d.get("id", "?")),
        date=case.get("EventDate") or d.get("EventDate"),
        title=_text(case.get("Title")) or _text(d.get("Title")),
    )


@mcp.tool(
    name="srgssr_polis_get_votations",
    description=(
        "Ruft Schweizer Volksabstimmungen und Referenden (national und kantonal) "
        "aus dem Polis-System ab. Liefert Datum, Titel und votation_id pro Eintrag.\n\n"
        "<use_case>Historische Analysen von Abstimmungsverhalten, journalistische "
        "Recherchen zu direkter Demokratie. Erster Schritt, um eine "
        "votation_id für srgssr_polis_get_votation_results zu ermitteln. Für "
        "Wahlen (Nationalrat, Ständerat) stattdessen "
        "srgssr_polis_get_elections.</use_case>\n\n"
        "<important_notes>Daten reichen zurück bis 1900. Der Kantonsfilter wird "
        "in eine locationid aufgelöst, der Jahresfilter in die Abstimmungstage "
        "des Zeitraums — ein Jahresbereich kostet deshalb mehrere Abfragen und "
        "sollte eng gesetzt werden. Paginiert mit page_size 1–100."
        "</important_notes>\n\n"
        "<example>year_from=2020, year_to=2024 | canton='ZH'</example>"
    ),
    annotations={
        "title": "SRG SSR Polis – Schweizer Abstimmungen",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def srgssr_polis_get_votations(
    params: PolisListInput,
    ctx: Context | None = None,
) -> VotationsResponse | ToolErrorResponse:
    log = logger.bind(
        tool="srgssr_polis_get_votations",
        year_from=params.year_from,
        year_to=params.year_to,
        canton=params.canton.upper() if params.canton else None,
        page=params.page,
        page_size=params.page_size,
    )
    log.info("tool_invoked")
    if ctx is not None:
        await ctx.info(
            "srgssr_polis_get_votations invoked",
            year_from=params.year_from,
            year_to=params.year_to,
            canton=params.canton,
        )
    try:
        raw_votations = await _fetch_filtered("votations", ("Items",), params)
    except Exception as e:
        log.error("tool_failed", error_type=type(e).__name__, error=str(e))
        return _build_error_response(e)

    # The API returns no total and no cursor, so the window is applied here.
    # `total` is the size of the filtered set we actually hold.
    total = len(raw_votations)
    start = (params.page - 1) * params.page_size
    page_items = raw_votations[start : start + params.page_size]
    log.info("tool_succeeded", result_count=len(page_items), total=total)

    votations = [_votation_from_dict(v) for v in page_items]
    return VotationsResponse(
        year_from=params.year_from,
        year_to=params.year_to,
        canton=(params.canton.upper() if params.canton else None),
        page=params.page,
        page_size=params.page_size,
        total=total,
        votations=votations,
        count=len(votations),
    )


@mcp.tool(
    name="srgssr_polis_get_votation_results",
    description=(
        "Ruft detaillierte Resultate einer einzelnen Schweizer Volksabstimmung ab "
        "(Ja/Nein-Anteile, Stimmbeteiligung, kantonale Ergebnisse, "
        "Annahme/Ablehnung).\n\n"
        "<use_case>Vertiefte politische Analysen, Visualisierung kantonaler "
        "Unterschiede.</use_case>\n\n"
        "<important_notes>Erfordert eine votation_id aus "
        "srgssr_polis_get_votations.</important_notes>\n\n"
        "<example>votation_id='v1'</example>"
    ),
    annotations={
        "title": "SRG SSR Polis – Abstimmungsresultate",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def srgssr_polis_get_votation_results(
    params: PolisResultInput,
    ctx: Context | None = None,
) -> VotationResultResponse | ToolErrorResponse:
    log = logger.bind(
        tool="srgssr_polis_get_votation_results",
        votation_id=params.votation_id,
    )
    log.info("tool_invoked")
    if ctx is not None:
        await ctx.info(
            "srgssr_polis_get_votation_results invoked",
            votation_id=params.votation_id,
        )
    try:
        data = await _api_get(f"{POLIS_BASE}/votations/{params.votation_id}", params={"lang": "de"})
    except Exception as e:
        log.error("tool_failed", error_type=type(e).__name__, error=str(e))
        return _build_error_response(
            e,
            not_found_hint=(
                f"votation_id='{params.votation_id}' nicht gefunden. Verwende "
                f"srgssr_polis_get_votations und übernimm die ID aus der Resultatliste."
            ),
        )

    log.info("tool_succeeded")

    return VotationResultResponse(
        votation_id=params.votation_id,
        title=_text(data.get("Title")),
        date=data.get("EventDate") or data.get("date"),
        result=data,
    )


@mcp.tool(
    name="srgssr_polis_get_elections",
    description=(
        "Ruft Schweizer Nationalrats-, Ständerats- und kantonale Wahlen aus "
        "dem Polis-System ab. Liefert Datum, Wahlbezeichnung und Wahl-ID.\n\n"
        "<use_case>Historische Wahlanalysen, journalistische "
        "Recherchen.</use_case>\n\n"
        "<important_notes>Daten reichen zurück bis 1900. Filter nach Jahr "
        "und Kanton möglich.</important_notes>\n\n"
        "<example>year_from=2023</example>"
    ),
    annotations={
        "title": "SRG SSR Polis – Schweizer Wahlen",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def srgssr_polis_get_elections(
    params: PolisListInput,
    ctx: Context | None = None,
) -> ElectionsResponse | ToolErrorResponse:
    log = logger.bind(
        tool="srgssr_polis_get_elections",
        year_from=params.year_from,
        year_to=params.year_to,
        canton=params.canton.upper() if params.canton else None,
        page=params.page,
        page_size=params.page_size,
    )
    log.info("tool_invoked")
    if ctx is not None:
        await ctx.info(
            "srgssr_polis_get_elections invoked",
            year_from=params.year_from,
            year_to=params.year_to,
            canton=params.canton,
        )
    try:
        raw_elections = await _fetch_filtered("elections", ("Elections", "Election"), params)
    except Exception as e:
        log.error("tool_failed", error_type=type(e).__name__, error=str(e))
        return _build_error_response(e)

    # The API returns no total and no cursor, so the window is applied here.
    # `total` is the size of the filtered set we actually hold.
    total = len(raw_elections)
    start = (params.page - 1) * params.page_size
    page_items = raw_elections[start : start + params.page_size]
    log.info("tool_succeeded", result_count=len(page_items), total=total)

    elections = [_election_from_dict(e, e.get("_case")) for e in page_items]
    return ElectionsResponse(
        year_from=params.year_from,
        year_to=params.year_to,
        canton=(params.canton.upper() if params.canton else None),
        page=params.page,
        page_size=params.page_size,
        total=total,
        elections=elections,
        count=len(elections),
    )
