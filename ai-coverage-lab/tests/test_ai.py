import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from coverage_lab.ai import analyze, build_payload, validate_insights
from coverage_lab.model import CoverageError
from tests import sample_report

ENV = {
    "COVERAGE_LAB_API_KEY": "test-not-a-real-key",
    "COVERAGE_LAB_MODEL": "test-model",
    "COVERAGE_LAB_ENDPOINT": "https://provider.example/v1",
}


def insight():
    return {
        "summary": "Test the missing path.",
        "recommendations": [
            {
                "path": "app.py",
                "lines": [2],
                "priority": "high",
                "reason": "Line 2 is unexecuted.",
                "test_idea": "Exercise the alternative branch.",
            }
        ],
    }


class AITests(unittest.TestCase):
    def test_payload_has_no_source_by_default(self):
        data = build_payload(sample_report())
        self.assertNotIn("source_excerpt", data["gaps"][0])
        self.assertNotIn("repository", data)

    def test_source_excerpts_are_explicit_and_cannot_escape_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "app.py").write_text("first\nmissing\nthird\n")
            data = build_payload(sample_report(), root, True)
            self.assertIn("2: missing", data["gaps"][0]["source_excerpt"])
            report = sample_report()
            report["files"][0]["path"] = "../outside.py"
            self.assertNotIn("source_excerpt", build_payload(report, root, True)["gaps"][0])
        with self.assertRaises(CoverageError):
            build_payload(sample_report(), None, True)

    def test_validate_rejects_invented_files_lines_and_invalid_shapes(self):
        for key, value in (
            ("path", "invented.py"),
            ("lines", [1]),
            ("lines", [True]),
            ("lines", []),
            ("priority", "critical"),
            ("reason", ""),
            ("test_idea", None),
        ):
            data = insight()
            data["recommendations"][0][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(CoverageError):
                validate_insights(data, sample_report())
        for data in (
            {},
            {"summary": "x", "recommendations": None},
            {"summary": "x", "recommendations": [None]},
            {"summary": "x", "recommendations": [{}] * 9},
        ):
            with self.assertRaises(CoverageError):
                validate_insights(data, sample_report())

    @patch.dict("os.environ", ENV, clear=True)
    @patch("coverage_lab.ai.urllib.request.build_opener")
    def test_provider_request_and_response_contract(self, build_opener):
        envelope = {"choices": [{"message": {"content": json.dumps(insight())}}]}
        build_opener.return_value.open.return_value = io.BytesIO(json.dumps(envelope).encode())
        result = analyze(sample_report())
        self.assertEqual(result["recommendations"][0]["lines"], [2])
        request = build_opener.return_value.open.call_args.args[0]
        self.assertEqual(request.full_url, "https://provider.example/v1/chat/completions")
        body = json.loads(request.data)
        self.assertEqual(body["model"], "test-model")
        self.assertNotIn("source_excerpt", body["messages"][1]["content"])
        self.assertFalse(result["source_shared"])

    @patch.dict("os.environ", ENV, clear=True)
    @patch("coverage_lab.ai.urllib.request.build_opener")
    def test_provider_failures_are_explicit_and_do_not_leak_response_bodies(self, build_opener):
        for error in (
            urllib.error.HTTPError("url", 401, "no", {}, None),
            urllib.error.URLError("secret-detail"),
            TimeoutError(),
        ):
            build_opener.return_value.open.side_effect = error
            with (
                self.subTest(error=type(error).__name__),
                self.assertRaises(CoverageError) as caught,
            ):
                analyze(sample_report())
            self.assertNotIn("secret-detail", str(caught.exception))

    @patch.dict("os.environ", ENV, clear=True)
    @patch("coverage_lab.ai.urllib.request.build_opener")
    def test_malformed_and_oversized_provider_responses_are_rejected(self, build_opener):
        for body in (b"{}", b"not-json", b"x" * (1024 * 1024 + 1)):
            build_opener.return_value.open.return_value = io.BytesIO(body)
            with self.assertRaises(CoverageError):
                analyze(sample_report())

    @patch.dict("os.environ", {}, clear=True)
    def test_missing_credentials_fail_not_fake_ai(self):
        with self.assertRaisesRegex(CoverageError, "requires"):
            analyze(sample_report())

    @patch.dict("os.environ", ENV, clear=True)
    def test_endpoint_must_be_https_and_have_no_credentials_or_query(self):
        for url in (
            "http://example.test",
            "https://key@example.test",
            "https://example.test?q=1",
            "https://example.test/#fragment",
        ):
            with patch.dict("os.environ", {"COVERAGE_LAB_ENDPOINT": url}):
                with self.assertRaises(CoverageError):
                    analyze(sample_report())

    @patch.dict("os.environ", ENV, clear=True)
    @patch("coverage_lab.ai.urllib.request.build_opener")
    def test_fully_covered_report_does_not_spend_ai_request(self, build_opener):
        report = sample_report()
        report["files"][0]["missing_lines"] = []
        report["files"][0]["partial_branch_lines"] = []
        result = analyze(report)
        self.assertEqual(result["recommendations"], [])
        build_opener.assert_not_called()

    def test_validated_insights_have_explicit_unverified_disclaimer(self):
        result = validate_insights(insight(), sample_report())
        self.assertIn("unverified", result["disclaimer"])
