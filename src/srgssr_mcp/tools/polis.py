"""Polis tools: Swiss votations, votation results, and elections (since 1900)."""

from mcp.server.fastmcp import Context
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


class PolisListInput(BaseModel):
    model_config = ConfigDict(strict=True, str_strip_whitespace=True, extra="forbid")
    year_from: int | None = Field(default=None, ge=1900, le=2100)
    year_to: int | None = Field(default=None, ge=1900, le=2100)
    canton: str | None = Field(
        default=None, min_length=2, max_length=4, pattern=r"^[A-Za-z]{2,4}$"
    )
    page_size: int | None = Field(default=20, ge=1, le=100)
    page: int | None = Field(default=1, ge=1)


class PolisResultInput(BaseModel):
    model_config = ConfigDict(strict=True, str_strip_whitespace=True, extra="forbid")
    votation_id: str = Field(
        ..., min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$"
    )


def _votation_from_dict(d: dict) -> Votation:
    return Votation(
        id=str(d.get("id", "?")),
        date=d.get("date") or d.get("votationDate"),
        title=d.get("title") or d.get("titleDe"),
    )


def _election_from_dict(d: dict) -> Election:
    return Election(
        id=str(d.get("id", "?")),
        date=d.get("date") or d.get("electionDate"),
        title=d.get("title") or d.get("titleDe"),
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
        "<important_notes>Daten reichen zurück bis 1900. Filter nach Jahr und "
        "Kanton möglich. Paginiert mit page_size 1–100.</important_notes>\n\n"
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
        query_params: dict = {
            "pageSize": params.page_size,
            "pageNumber": params.page,
        }
        if params.year_from:
            query_params["yearFrom"] = params.year_from
        if params.year_to:
            query_params["yearTo"] = params.year_to
        if params.canton:
            query_params["canton"] = params.canton.upper()

        data = await _api_get(f"{POLIS_BASE}/votations", params=query_params)
    except Exception as e:
        log.error("tool_failed", error_type=type(e).__name__, error=str(e))
        return _build_error_response(e)

    raw_votations = data.get("votationList", data.get("votations", [])) or []
    total = int(data.get("total", len(raw_votations)))
    log.info("tool_succeeded", result_count=len(raw_votations), total=total)

    votations = [_votation_from_dict(v) for v in raw_votations]
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
        data = await _api_get(f"{POLIS_BASE}/votations/{params.votation_id}")
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
        title=data.get("title") or data.get("titleDe"),
        date=data.get("date") or data.get("votationDate"),
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
        query_params: dict = {
            "pageSize": params.page_size,
            "pageNumber": params.page,
        }
        if params.year_from:
            query_params["yearFrom"] = params.year_from
        if params.year_to:
            query_params["yearTo"] = params.year_to
        if params.canton:
            query_params["canton"] = params.canton.upper()

        data = await _api_get(f"{POLIS_BASE}/elections", params=query_params)
    except Exception as e:
        log.error("tool_failed", error_type=type(e).__name__, error=str(e))
        return _build_error_response(e)

    raw_elections = data.get("electionList", data.get("elections", [])) or []
    total = int(data.get("total", len(raw_elections)))
    log.info("tool_succeeded", result_count=len(raw_elections), total=total)

    elections = [_election_from_dict(e) for e in raw_elections]
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
