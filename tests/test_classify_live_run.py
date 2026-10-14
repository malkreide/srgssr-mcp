#!/usr/bin/env python3
"""Tests fuer scripts/classify_live_run.py — die drei Antworten eines Live-Laufs.

Die Einordnung entscheidet, ob ein Issue aufgeht oder zugeht. Genau deshalb
steht sie in einem Skript und nicht in einem `run:`-Block: So kann jemand sie
gegen die Faelle halten, aus denen sie entstanden ist.

Der wichtigste Fall ist `test_alle_uebersprungen_ist_nicht_gruen`. Gemessen am
7.8.2026 an `swiss-transport-mcp`: Ohne `TRANSPORT_API_KEY` ueberspringt die
Live-Suite alle sechs Tests und pytest endet mit 0. Ein Job, der das als gruen
bucht, schliesst ein offenes Issue mit einem Vergleich, den es nie gab.

Kein Netz. `FailureDetailTest` zieht das Paket selbst heran, weil es die
Meldung des Werkzeugs gegen die Einordnung haelt, statt sie abzuschreiben.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from xml.sax.saxutils import quoteattr

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import classify_live_run as clr  # noqa: E402


def write(tmp: Path, xml: str) -> Path:
    path = tmp / "live-report.xml"
    path.write_text(xml, encoding="utf-8")
    return path


def suite(tests: int, failures: int = 0, errors: int = 0, skipped: int = 0) -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        f'<testsuites><testsuite name="pytest" tests="{tests}" failures="{failures}" '
        f'errors="{errors}" skipped="{skipped}"></testsuite></testsuites>'
    )


def cases(*failed: tuple[str, str], tests: int = 15) -> str:
    """Ein Report mit gefallenen Testfaellen, je (Name, message-Attribut)."""
    body = "".join(
        f'<testcase classname="tests.test_live" name="{name}">'
        f"<failure message={quoteattr(message)}>Traceback</failure></testcase>"
        for name, message in failed
    )
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        f'<testsuites><testsuite name="pytest" tests="{tests}" failures="{len(failed)}" '
        f'errors="0" skipped="0">{body}</testsuite></testsuites>'
    )


def tool_message(status: int, body: str = "nope") -> str:
    """Was das Werkzeug bei diesem Status wirklich meldet — nicht abgeschrieben."""
    import httpx

    from srgssr_mcp._http import _handle_error

    req = httpx.Request("GET", "https://api.srgssr.ch/polis-api/v2/cases")
    err = httpx.HTTPStatusError("x", request=req, response=httpx.Response(status, text=body, request=req))
    return f"AssertionError: HTTPStatusError: {_handle_error(err)}"


def cli(*extra: str) -> tuple[str, str]:
    """Ruft `main` mit gesetztem $GITHUB_OUTPUT und liest zurueck, was ankam."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "gh-output"
        out.write_text("", encoding="utf-8")
        os.environ["GITHUB_OUTPUT"] = str(out)
        try:
            clr.main([str(Path(tmp) / "live-report.xml"), *extra])
        finally:
            del os.environ["GITHUB_OUTPUT"]
        written = out.read_text(encoding="utf-8")
    werte = dict(line.split("=", 1) for line in written.splitlines() if line)
    return werte["state"], werte["reason"]


class ClassifyTest(unittest.TestCase):
    def _state(self, xml: str) -> tuple[str, str]:
        with tempfile.TemporaryDirectory() as tmp:
            return clr.classify(write(Path(tmp), xml))

    def test_alles_gruen_ist_clear(self):
        state, reason = self._state(suite(tests=3))
        self.assertEqual(state, clr.CLEAR)
        self.assertIn("3 von 3", reason)

    def test_ein_fehlschlag_ist_ein_finding(self):
        state, _ = self._state(suite(tests=3, failures=1))
        self.assertEqual(state, clr.FINDING)

    def test_ein_fehler_ist_ein_finding(self):
        state, _ = self._state(suite(tests=3, errors=1))
        self.assertEqual(state, clr.FINDING)

    def test_alle_uebersprungen_ist_nicht_gruen(self):
        """swiss-transport-mcp ohne TRANSPORT_API_KEY: 6 von 6 uebersprungen."""
        state, reason = self._state(suite(tests=6, skipped=6))
        self.assertEqual(state, clr.UNKNOWN)
        self.assertIn("uebersprungen", reason)

    def test_teilweise_uebersprungen_ist_gruen(self):
        """Ein einzelner Skip ist eine Entscheidung im Test, kein Ausfall."""
        state, reason = self._state(suite(tests=6, skipped=5))
        self.assertEqual(state, clr.CLEAR)
        self.assertIn("1 von 6", reason)

    def test_null_tests_ist_kein_erfolg(self):
        """Die Marke umbenannt, die Dateien verschoben — pytest meldet trotzdem 0."""
        state, reason = self._state(suite(tests=0))
        self.assertEqual(state, clr.UNKNOWN)
        self.assertIn("null Tests", reason)

    def test_ein_fehlschlag_schlaegt_uebersprungene(self):
        state, _ = self._state(suite(tests=6, skipped=5, failures=1))
        self.assertEqual(state, clr.FINDING)

    def test_mehrere_testsuites_werden_summiert(self):
        xml = (
            "<testsuites>"
            '<testsuite tests="2" failures="0" errors="0" skipped="2"/>'
            '<testsuite tests="3" failures="0" errors="0" skipped="0"/>'
            "</testsuites>"
        )
        state, _ = self._state(xml)
        self.assertEqual(state, clr.CLEAR)

    def test_eine_einzelne_testsuite_ohne_huelle(self):
        xml = '<testsuite tests="2" failures="0" errors="0" skipped="0"/>'
        state, _ = self._state(xml)
        self.assertEqual(state, clr.CLEAR)


class FailureDetailTest(unittest.TestCase):
    """Ein Finding nennt, was gefallen ist — und ob die Quelle ueberhaupt antwortete.

    Vom 9.10.2026 an fielen jede Nacht dieselben drei Polis-Tests mit HTTP 503
    vom Gateway. Das Issue darueber hiess «possible API schema drift», die
    Kommentare sagten nur «Still failing». Ein Schema laesst sich nur an einer
    Antwort pruefen, und es kam keine.
    """

    POLIS = ("test_live_polis_get_votations", "test_live_polis_get_elections", "test_live_polis_get_votation_results")

    def _state(self, xml: str) -> tuple[str, str]:
        with tempfile.TemporaryDirectory() as tmp:
            return clr.classify(write(Path(tmp), xml))

    def test_der_polis_ausfall_heisst_nicht_erreichbar(self):
        state, reason = self._state(cases(*((name, tool_message(503)) for name in self.POLIS)))
        self.assertEqual(state, clr.FINDING, "ein Ausfall gehoert weiter ins Issue")
        self.assertIn("Quelle nicht erreichbar (HTTP 503)", reason)
        self.assertIn("ueber das Schema sagt dieser Lauf nichts", reason)
        for name in self.POLIS:
            self.assertIn(name, reason)

    def test_eine_gefallene_zusicherung_bleibt_ohne_status(self):
        """Der Fall, fuer den das Issue geschrieben ist: ein Feld fehlt."""
        _, reason = self._state(
            cases(("test_live_polis_get_votation_results", "AssertionError: Live votation payload missing 'id'"))
        )
        self.assertIn("test_live_polis_get_votation_results (ohne HTTP-Status)", reason)
        self.assertNotIn("nicht erreichbar", reason)

    def test_ein_500_ist_eine_antwort_der_quelle(self):
        _, reason = self._state(cases(("test_live_epg_get_programs", tool_message(500))))
        self.assertIn("test_live_epg_get_programs (HTTP 500)", reason)
        self.assertNotIn("nicht erreichbar", reason)

    def test_gemischt_wird_jeder_fall_einzeln_benannt(self):
        _, reason = self._state(
            cases(
                ("test_a", tool_message(503)),
                ("test_b", tool_message(404)),
                ("test_c", "AssertionError: expected a schedule for srf-1"),
            )
        )
        self.assertIn("test_a (HTTP 503, Quelle nicht erreichbar)", reason)
        self.assertIn("test_b (HTTP 404)", reason)
        self.assertIn("test_c (ohne HTTP-Status)", reason)
        self.assertNotIn("ueber das Schema sagt dieser Lauf nichts", reason, "nicht alles war ein Ausfall")

    def test_ohne_testfaelle_bleibt_es_bei_den_zahlen(self):
        """Eine leere Liste ist kein «alle nicht erreichbar»."""
        _, reason = self._state(suite(tests=3, failures=1))
        self.assertEqual(reason, "1 Fehlschlag/Fehlschlaege und 0 Fehler von 3 Test(s)")

    def test_ein_status_im_traceback_zaehlt_nicht(self):
        """Im Traceback steht der Quelltext des Tests — dort ist «Fehler 503» kein Befund."""
        xml = (
            '<testsuite tests="1" failures="1" errors="0" skipped="0">'
            '<testcase name="test_x"><failure message="AssertionError: kein Feld">'
            "# Fehler 503 kam hier am 9.10. vor</failure></testcase></testsuite>"
        )
        _, reason = self._state(xml)
        self.assertIn("test_x (ohne HTTP-Status)", reason)

    def test_dieselben_stati_wie_das_werkzeug(self):
        from srgssr_mcp._http import UPSTREAM_UNAVAILABLE_STATUSES

        self.assertEqual(clr.UNREACHABLE, UPSTREAM_UNAVAILABLE_STATUSES)

    def test_ein_echter_bericht_ohne_v_traegt_den_status(self):
        """pytest selbst schreibt den Report, mit dem echten `_describe` aus test_live.

        Ein Objekt als Zusicherungsmeldung kuerzt pytest ohne `-v` auf 240
        Zeichen; am 14.10.2026 fiel der Schnitt genau vor den Status. Nur ein
        echter Lauf zeigt, ob er im `message`-Attribut ankommt.
        """
        root = Path(__file__).resolve().parents[1]
        probe = textwrap.dedent(
            """
            import httpx

            from srgssr_mcp._http import _build_error_response
            from tests.test_live import _describe, _is_error

            def test_live_polis_get_votations():
                req = httpx.Request("GET", "https://api.srgssr.ch/polis-api/v2/cases")
                resp = httpx.Response(503, text="{}", request=req)
                result = _build_error_response(httpx.HTTPStatusError("x", request=req, response=resp))
                assert not _is_error(result), _describe(result)
            """
        )
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "test_probe.py").write_text(probe, encoding="utf-8")
            report = Path(tmp) / "live-report.xml"
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "-p",
                    "no:cacheprovider",
                    "-c",
                    os.devnull,
                    "--rootdir",
                    tmp,
                    f"--junitxml={report}",
                    str(Path(tmp) / "test_probe.py"),
                ],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=120,
            )
            self.assertEqual(proc.returncode, 1, f"die Probe sollte genau fallen:\n{proc.stdout}\n{proc.stderr}")
            state, reason = clr.classify(report)
        self.assertEqual(state, clr.FINDING)
        self.assertIn("Quelle nicht erreichbar (HTTP 503)", reason)


class MissingReportTest(unittest.TestCase):
    """Kein Report heisst: pytest kam nicht bis zum Schreiben. Nie clear."""

    def test_fehlender_report_ist_unknown(self):
        state, reason = clr.classify(Path("/nonexistent/live-report.xml"), pytest_exit=4)
        self.assertEqual(state, clr.UNKNOWN)
        self.assertIn("Exit 4", reason)

    def test_kaputtes_xml_ist_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(Path(tmp), "<testsuite tests=")
            state, _ = clr.classify(path)
        self.assertEqual(state, clr.UNKNOWN)

    def test_xml_ohne_testsuite_ist_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(Path(tmp), "<irgendwas/>")
            state, _ = clr.classify(path)
        self.assertEqual(state, clr.UNKNOWN)


class NotStartedTest(unittest.TestCase):
    """pytest nie aufgerufen: Der Grund kommt vom Aufrufer, nicht vom Exit-Code.

    Beobachtet am 24.8.2026 in `swiss-ip-mcp`: Ohne Zugangsdaten meldete der
    Workflow `--pytest-exit 127`, und daraus wurde «pytest ist nicht bis zum
    Schreiben gekommen (Exit 127)». 127 heisst «command not found» — der Satz
    behauptete einen gescheiterten pytest-Aufruf, den es nie gab.
    """

    def test_grund_wird_woertlich_durchgereicht(self):
        state, reason = clr.classify(
            Path("/nonexistent/live-report.xml"),
            not_started="Secret ist nicht gesetzt",
        )
        self.assertEqual(state, clr.UNKNOWN)
        self.assertEqual(reason, "Secret ist nicht gesetzt")

    def test_kein_erfundener_pytest_lauf_in_der_begruendung(self):
        _, reason = clr.classify(
            Path("/nonexistent/live-report.xml"),
            not_started="Secret ist nicht gesetzt",
        )
        self.assertNotIn("pytest ist nicht bis zum Schreiben gekommen", reason)
        self.assertNotIn("Exit", reason)

    def test_ein_liegengebliebener_report_belegt_nichts(self):
        """Gruenes XML aus einem frueheren Schritt macht einen Nicht-Lauf nicht gruen."""
        with tempfile.TemporaryDirectory() as tmp:
            report = write(Path(tmp), suite(tests=3))
            state, reason = clr.classify(report, not_started="gar nicht gestartet")
        self.assertEqual(state, clr.UNKNOWN)
        self.assertEqual(reason, "gar nicht gestartet")

    def test_leerer_grund_ist_kein_grund(self):
        """Der Workflow reicht `--not-started` nur gesetzt durch; leer heisst: pytest lief."""
        with tempfile.TemporaryDirectory() as tmp:
            report = write(Path(tmp), suite(tests=3))
            state, _ = clr.classify(report, not_started="")
        self.assertEqual(state, clr.CLEAR)

    def test_ueber_die_kommandozeile(self):
        state, reason = cli("--not-started", "kein Secret")
        self.assertEqual(state, "unknown")
        self.assertEqual(reason, "kein Secret")


class GithubOutputTest(unittest.TestCase):
    """Der Workflow liest state und reason ueber $GITHUB_OUTPUT."""

    def test_beide_werte_werden_angehaengt(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = write(Path(tmp), suite(tests=2))
            out = Path(tmp) / "gh-output"
            out.write_text("", encoding="utf-8")
            os.environ["GITHUB_OUTPUT"] = str(out)
            try:
                rc = clr.main([str(report)])
            finally:
                del os.environ["GITHUB_OUTPUT"]
            written = out.read_text(encoding="utf-8")
        self.assertEqual(rc, 0)
        self.assertIn("state=clear", written)
        self.assertIn("reason=", written)

    def test_ein_mehrzeiliger_grund_schiebt_kein_zweites_output_nach(self):
        """`key=value` endet an der ersten neuen Zeile — was danach steht, ist Output."""
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "gh-output"
            out.write_text("", encoding="utf-8")
            os.environ["GITHUB_OUTPUT"] = str(out)
            try:
                clr.main(
                    [
                        str(Path(tmp) / "live-report.xml"),
                        "--not-started",
                        "kein Secret\nstate=clear",
                    ]
                )
            finally:
                del os.environ["GITHUB_OUTPUT"]
            zeilen = [z for z in out.read_text(encoding="utf-8").splitlines() if z]
        self.assertEqual([z for z in zeilen if z.startswith("state=")], ["state=unknown"])
        self.assertEqual(len(zeilen), 2)


if __name__ == "__main__":
    unittest.main()
