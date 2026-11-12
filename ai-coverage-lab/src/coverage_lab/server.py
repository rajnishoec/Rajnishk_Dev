"""Small loopback dashboard: report uploads and optional AI, never test execution."""

import json
import secrets
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files

from coverage_lab.ai import analyze
from coverage_lab.model import CoverageError, prioritize
from coverage_lab.reports import MAX_REPORT_BYTES, parse_report


def make_server(port: int = 8765) -> ThreadingHTTPServer:
    token = secrets.token_urlsafe(32)
    html = files("coverage_lab").joinpath("static/index.html").read_text(encoding="utf-8")
    html = html.replace("__CSRF_TOKEN__", token)

    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
                "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
            )
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, data: dict) -> None:
            self._send(status, json.dumps(data).encode(), "application/json; charset=utf-8")

        def _valid_host(self) -> bool:
            return self.headers.get("Host") in {
                f"127.0.0.1:{self.server.server_port}",
                f"localhost:{self.server.server_port}",
            }

        def do_GET(self) -> None:
            if not self._valid_host():
                self._json(403, {"error": "Only loopback hosts are accepted."})
            elif self.path == "/":
                self._send(200, html.encode(), "text/html; charset=utf-8")
            elif self.path == "/api/health":
                self._json(200, {"status": "ok"})
            else:
                self._json(404, {"error": "Not found."})

        def do_POST(self) -> None:
            origin = self.headers.get("Origin")
            allowed = {
                f"http://127.0.0.1:{self.server.server_port}",
                f"http://localhost:{self.server.server_port}",
            }
            if not self._valid_host() or (origin is not None and origin not in allowed):
                self._json(403, {"error": "Cross-origin requests are not accepted."})
                return
            if not secrets.compare_digest(self.headers.get("X-Coverage-Token", ""), token):
                self._json(403, {"error": "Invalid session token; refresh the dashboard."})
                return
            path = urllib.parse.urlsplit(self.path)
            if path.path != "/api/report":
                self._json(404, {"error": "Not found."})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= MAX_REPORT_BYTES:
                    self._json(413, {"error": "Supply a report no larger than 25 MiB."})
                    return
                text = self.rfile.read(length).decode("utf-8-sig")
                report = parse_report(text).to_dict()
                report["priorities"] = prioritize(report)
                if urllib.parse.parse_qs(path.query).get("ai") == ["true"]:
                    report["ai"] = analyze(report)
                self._json(200, report)
            except (CoverageError, ValueError, UnicodeError) as error:
                self._json(400, {"error": str(error)})

        def log_message(self, format: str, *args) -> None:
            # Do not log uploaded filenames, report bodies, prompts, or credentials.
            return

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    return server


def serve_dashboard(port: int) -> None:
    with make_server(port) as server:
        print(f"Coverage Lab: http://127.0.0.1:{server.server_port}", flush=True)
        print(
            "Upload reports only. Run repository tests explicitly with coverage-lab run.",
            flush=True,
        )
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
