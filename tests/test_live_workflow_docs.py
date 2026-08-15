"""The CONTRIBUTING paragraphs about the live suite match the workflow itself.

Those paragraphs state a cadence, an issue title and a dedupe rule. Prose can
drift from the workflow silently — nothing fails when a cron changes and a
sentence does not. The commit that introduced them claimed a machine
cross-check, but shipped only the two markdown files, so nothing was left
behind that could catch the drift later. These tests are that check.

They read both files and compare, rather than restating the values: a test that
hardcodes what the docs *should* say is written from the same assumption as the
docs and cannot contradict them.
"""

from __future__ import annotations

import pathlib
import re

import pytest

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_WORKFLOW = _ROOT / ".github" / "workflows" / "live-test.yml"
_DOCS = (_ROOT / "CONTRIBUTING.md", _ROOT / "CONTRIBUTING.de.md")


def _workflow_text() -> str:
    return _WORKFLOW.read_text()


def _notify_step() -> str:
    """The `Notify on failure` step, up to the next step at the same indent."""
    text = _workflow_text()
    start = text.index("- name: Notify on failure")
    rest = text[start + 1 :]
    end = rest.find("\n      - name:")
    return rest if end == -1 else rest[:end]


@pytest.mark.parametrize("doc", _DOCS, ids=lambda p: p.name)
def test_the_documented_issue_title_is_the_one_the_workflow_files(doc: pathlib.Path):
    """The title is the dedupe key, so a stale copy in the docs misleads twice.

    It tells the reader to look for a heading that never appears, and it hides
    that editing the title is what breaks deduplication.
    """
    match = re.search(r'const title = "([^"]+)"', _workflow_text())
    assert match, "could not find the issue title in the workflow — the scan is broken"
    assert match.group(1) in doc.read_text(), (
        f"{doc.name} does not quote the title the workflow actually files: {match.group(1)!r}"
    )


@pytest.mark.parametrize("doc", _DOCS, ids=lambda p: p.name)
def test_the_documented_label_is_the_one_the_workflow_applies(doc: pathlib.Path):
    labels = re.search(r"labels: \[([^\]]+)\]", _workflow_text())
    assert labels, "could not find the issue labels in the workflow — the scan is broken"
    for label in re.findall(r'"([^"]+)"', labels.group(1)):
        if label == "bug":  # generic, not worth naming in prose
            continue
        assert label in doc.read_text(), f"{doc.name} does not mention the {label!r} label"


@pytest.mark.parametrize("doc", _DOCS, ids=lambda p: p.name)
def test_the_documented_hour_is_the_one_the_cron_runs(doc: pathlib.Path):
    """`0 4 * * *` and "04:00 UTC" have to stay in step."""
    cron = re.search(r'cron: "(\S+) (\S+) \S+ \S+ \S+"', _workflow_text())
    assert cron, "could not find the cron in the workflow — the scan is broken"
    minute, hour = cron.group(1), cron.group(2)
    stamp = f"{int(hour):02d}:{int(minute):02d}"
    assert stamp in doc.read_text(), f"{doc.name} does not state the cron's actual time ({stamp} UTC)"


def test_a_hand_started_red_run_reports_too():
    """The notify step must not be gated back onto the schedule.

    It was `if: failure() && github.event_name == 'schedule'`, which made the
    manual trigger a trap: a run started to check a suspected drift went red and
    filed nothing. Both CONTRIBUTING files now promise the opposite.
    """
    step = _notify_step()
    assert "if: failure()" in step, "the notify step no longer runs on failure"
    assert "event_name == 'schedule'" not in step, (
        "the notify step is gated on the schedule again — a hand-started red run "
        "would file nothing, while both CONTRIBUTING files promise it reports."
    )
