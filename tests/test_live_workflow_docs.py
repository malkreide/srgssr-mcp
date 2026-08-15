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

import json
import pathlib
import re
import shutil
import subprocess
import textwrap

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
    lines = [ln for ln in step.splitlines() if not ln.lstrip().startswith(("#", "//"))]
    assert "event_name == 'schedule'" not in "\n".join(lines), (
        "the notify step is gated on the schedule again — a hand-started red run "
        "would file nothing, while both CONTRIBUTING files promise it reports."
    )


# --- The dedupe, run rather than read ---------------------------------------


def _notify_script() -> str:
    """The JavaScript body of the notify step, dedented."""
    step = _notify_step()
    marker = "script: |"
    body = step[step.index(marker) + len(marker) :].lstrip("\n")
    kept = []
    for line in body.splitlines():
        if line.strip() and not line.startswith(" " * 12):
            break
        kept.append(line)
    return textwrap.dedent("\n".join(kept))


def _run_notify(event_name: str, open_issues: list[dict]) -> list[dict]:
    """Execute the real notify script against a stubbed GitHub API.

    Asserting that the source contains ``startsWith`` would also pass for
    ``startsWith(runUrl)``. Running it is the only way to find out what it
    actually treats as the same report.
    """
    harness = f"""
    const OPEN = {json.dumps(open_issues)};
    const calls = [];
    const context = {{
      serverUrl: "https://github.com",
      repo: {{ owner: "o", repo: "r" }},
      runId: 42,
      eventName: {json.dumps(event_name)},
    }};
    const github = {{
      paginate: async () => OPEN,
      rest: {{ issues: {{
        listForRepo: () => {{}},
        createComment: async (a) => {{ calls.push({{ op: "comment", ...a }}); }},
        create: async (a) => {{ calls.push({{ op: "create", ...a }}); }},
      }} }},
    }};
    async function __step() {{
    {textwrap.indent(_notify_script(), "    ")}
    }}
    await __step();
    console.log(JSON.stringify(calls));
    """
    proc = subprocess.run(
        ["node", "--input-type=module", "-e", textwrap.dedent(harness)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, f"notify script failed to run:\n{proc.stderr}"
    return json.loads(proc.stdout)


_TITLE = "Live tests failed (possible API schema drift)"
_NEEDS_NODE = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")


def test_the_extracted_script_is_the_real_one():
    """Guards the tests below against silently running on an empty extraction.

    Without this, a broken extractor would make every behavioural assertion
    below vacuous — and they would all still pass.
    """
    script = _notify_script()
    assert "issues.create" in script and "createComment" in script, f"extraction looks wrong:\n{script[:200]}"


@_NEEDS_NODE
def test_an_appended_title_still_counts_as_the_same_report():
    """The point of the prefix match: annotation must not fork the thread."""
    calls = _run_notify("schedule", [{"number": 7, "title": f"{_TITLE} — seit dem 15.8."}])
    assert [c["op"] for c in calls] == ["comment"], "an annotated title opened a second issue"
    assert calls[0]["issue_number"] == 7


@_NEEDS_NODE
def test_an_unrelated_open_issue_does_not_swallow_the_report():
    """The prefix must not be so loose that any labelled issue absorbs it."""
    calls = _run_notify("schedule", [{"number": 9, "title": "Flaky live test on Sundays"}])
    assert [c["op"] for c in calls] == ["create"], "an unrelated issue was mistaken for the drift report"
    assert calls[0]["title"] == _TITLE


@_NEEDS_NODE
@pytest.mark.parametrize(
    ("event_name", "expected"),
    [("schedule", "Nightly run"), ("workflow_dispatch", "Manual run")],
)
def test_the_body_names_the_trigger(event_name: str, expected: str):
    calls = _run_notify(event_name, [])
    assert calls[0]["op"] == "create"
    assert calls[0]["body"].startswith(f"{expected}: live tests")
