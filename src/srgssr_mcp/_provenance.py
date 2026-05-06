"""Provenance helpers for tool outputs (CH-004 / SDK-002 partial).

Every tool emits Markdown by default and JSON when the caller passes
``response_format=ResponseFormat.JSON``. Both branches go through the
helpers below so the source-of-truth attribution is consistent.

Design choice — *non-breaking*:

* JSON envelope is **additive**: provenance fields are inserted at the
  top level alongside the existing keys. Consumers that look up specific
  upstream keys (``geolocationList``, ``currentForecast``, …) keep working;
  consumers that want the metadata can read ``source`` / ``license`` etc.
* Markdown footer is **appended** after a horizontal rule. Existing
  substring assertions in tests stay green; readers see a clear
  separation between data and attribution.

For full SDK-002 compliance (typed Pydantic Response models in the tool
signature) we will need a follow-up Breaking-Change PR. This module
unblocks CH-004 (machine-readable provenance + README licence table)
without that churn.
"""

from __future__ import annotations

from datetime import UTC, datetime

SOURCE = "SRG SSR Public API V2"
LICENSE = "SRG SSR Terms of Use (non-commercial; commercial use requires written permission via api@srgssr.ch)"
PROVENANCE_URL = "https://developer.srgssr.ch"


def _now_iso() -> str:
    """ISO-8601 UTC timestamp with a stable second-precision shape for tests."""
    return datetime.now(UTC).isoformat(timespec="seconds")


def with_provenance(payload: dict | list, list_key: str = "results") -> dict:
    """Return ``payload`` augmented with top-level provenance fields.

    For a ``dict`` payload the original keys are preserved unchanged so
    existing JSON consumers that look up ``currentForecast`` /
    ``geolocationList`` / ``programList`` etc. continue to work.

    For a ``list`` payload the items are placed under ``list_key``
    (default ``"results"``) and a ``count`` field is added — this matches
    the Response-envelope shape recommended by SDK-002.
    """
    base = {
        "source": SOURCE,
        "license": LICENSE,
        "provenance_url": PROVENANCE_URL,
        "fetched_at": _now_iso(),
    }
    if isinstance(payload, list):
        return {**base, list_key: payload, "count": len(payload)}
    return {**base, **payload}


def provenance_footer() -> str:
    """Markdown footer block with source attribution.

    Always begins with a leading newline + horizontal rule so it can be
    appended directly to any Markdown body without the caller worrying
    about trailing whitespace.
    """
    return (
        "\n\n---\n"
        f"_Quelle: {SOURCE} · "
        f"Lizenz: SRG SSR Terms of Use (non-commercial) · "
        f"Bezug: {PROVENANCE_URL}_"
    )
