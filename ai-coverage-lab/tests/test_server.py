import json
import re
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

from coverage_lab.server import make_server
from tests import LCOV


class DashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = make_server(0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"
        with urllib.request.urlopen(cls.base) as response:
            cls.html = response.read().decode()
        cls.token = re.search(r'const token = "([^"]+)"', cls.html)[1]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def post(self, content=LCOV, token=None, suffix="", extra=None):
        headers = {"X-Coverage-Token": token if token is not None else self.token}
        headers.update(extra or {})
        return urllib.request.urlopen(
            urllib.request.Request(
                self.base + "/api/report" + suffix,
                data=content.encode(),
                headers=headers,
                method="POST",
            )
        )

    def test_health_and_html_resources(self):
        self.assertIn("Measured code.", self.html)
        self.assertNotIn("__CSRF_TOKEN__", self.html)
        with urllib.request.urlopen(self.base + "/api/health") as response:
            self.assertEqual(json.load(response)["status"], "ok")
            self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")

    def test_upload_and_download_format_roundtrip(self):
        with self.post() as response:
            report = json.load(response)
        self.assertEqual(report["totals"]["lines"]["percent"], 66.67)
        with self.post(json.dumps(report)) as response:
            self.assertEqual(json.load(response)["files"][0]["missing_lines"], [2])

    def test_invalid_token_origin_and_host_are_rejected(self):
        for kwargs in (
            {"token": "wrong"},
            {"extra": {"Origin": "https://other.example"}},
            {"extra": {"Host": "attacker.example"}},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(urllib.error.HTTPError) as error:
                self.post(**kwargs)
            self.assertEqual(error.exception.code, 403)
            error.exception.close()

    def test_bad_report_and_unknown_routes(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.post("not coverage")
        self.assertEqual(error.exception.code, 400)
        error.exception.close()
        for path in ("/missing", "/api/run"):
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(self.base + path)
            self.assertEqual(error.exception.code, 404)
            error.exception.close()

    @patch(
        "coverage_lab.server.analyze", return_value={"summary": "contract", "recommendations": []}
    )
    def test_ai_request_is_explicit_and_does_not_read_source(self, analyze):
        with self.post(suffix="?ai=true") as response:
            self.assertEqual(json.load(response)["ai"]["summary"], "contract")
        self.assertEqual(len(analyze.call_args.args), 1)

    def test_empty_report_is_not_success(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.post("")
        self.assertEqual(error.exception.code, 413)
        error.exception.close()
