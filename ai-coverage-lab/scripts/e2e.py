"""Verify both actual toolchains, report imports, thresholds, HTTP, and optional browser UI."""

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.request
from pathlib import Path

from coverage_lab.server import make_server


def run_cli(*arguments, expected=0):
    result = subprocess.run(
        [sys.executable, "-m", "coverage_lab", *map(str, arguments)],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    if result.returncode != expected:
        raise AssertionError(f"CLI exit {result.returncode}, expected {expected}\n{result.stderr}")
    return json.loads(result.stdout) if result.stdout else None


def verify(sample: Path, browser: bool = False):
    with tempfile.TemporaryDirectory(prefix="coverage-lab-e2e-") as directory:
        root = Path(directory)
        repo = root / "sample"
        shutil.copytree(
            sample,
            repo,
            ignore=shutil.ignore_patterns(".git", ".venv", "coverage", "__pycache__", "*.egg-info"),
        )
        reports = {}
        for runner, filename in (("python", "invoice.py"), ("npm", "javascript/pricing.js")):
            result = run_cli("run", repo, "--runner", runner, "--output", root / f"{runner}.json")
            assert 0 < result["totals"]["lines"]["percent"] < 100, result
            assert result["totals"]["branches"]["total"] > 0, result
            file = next(file for file in result["files"] if file["path"] == filename)
            assert file["missing_lines"], file
            reports[runner] = result
            print(
                f"{runner}: {result['totals']['lines']['percent']}% lines, "
                f"{result['totals']['branches']['percent']}% branches; gaps detected"
            )
        # Fresh npm output is required; the second run must reject the stale report.
        assert run_cli("run", repo, "--runner", "npm", expected=1) is None
        threshold = run_cli("report", root / "python.json", "--fail-under", "100", expected=2)
        assert threshold["totals"]["lines"]["percent"] < 100
        imported = run_cli("report", repo / "coverage" / "lcov.info")
        assert imported["totals"] == reports["npm"]["totals"]
        xml = root / "coverage.xml"
        xml.write_text("""<coverage><packages><package><classes><class filename="sample.cs"><lines>
        <line number="1" hits="1"/><line number="2" hits="0" branch="true"
        condition-coverage="50% (1/2)"/></lines></class></classes></package></packages></coverage>""")
        assert run_cli("report", xml)["totals"]["branches"]["percent"] == 50
        with make_server(0) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            url = f"http://127.0.0.1:{server.server_port}"
            try:
                with urllib.request.urlopen(url) as response:
                    token = re.search(r'const token = "([^"]+)"', response.read().decode())[1]
                request = urllib.request.Request(
                    url + "/api/report",
                    data=(root / "python.json").read_bytes(),
                    headers={"X-Coverage-Token": token},
                    method="POST",
                )
                with urllib.request.urlopen(request) as response:
                    assert json.load(response)["totals"] == reports["python"]["totals"]
                if browser:
                    from playwright.sync_api import sync_playwright

                    with sync_playwright() as playwright:
                        browser_instance = playwright.chromium.launch(
                            channel="msedge" if sys.platform == "win32" else None,
                            headless=True,
                        )
                        try:
                            page = browser_instance.new_page(
                                viewport={"width": 1280, "height": 1000}
                            )
                            errors = []
                            page.on("pageerror", lambda error: errors.append(str(error)))
                            page.goto(url)
                            page.locator("#file").set_input_files(str(root / "python.json"))
                            page.get_by_role("button", name="Analyze coverage").click()
                            page.locator("#results").wait_for(state="visible")
                            assert "invoice.py" in page.locator("#file-rows").inner_text()
                            assert "%" in page.locator("#line-value").inner_text()
                            assert page.locator("#ai-panel").is_hidden()
                            assert not errors, errors
                            screenshot = Path("artifacts") / "dashboard.png"
                            screenshot.parent.mkdir(exist_ok=True)
                            page.screenshot(path=str(screenshot), full_page=True)
                            page.set_viewport_size({"width": 390, "height": 844})
                            assert page.evaluate(
                                "document.documentElement.scrollWidth <= window.innerWidth"
                            ), "Mobile page overflows horizontally"
                            print(f"Browser: rendered metrics, gaps, no JS errors; {screenshot}")
                        finally:
                            browser_instance.close()
            finally:
                server.shutdown()
                thread.join(timeout=5)
        print(
            "PASS: real Python/npm runs, missing branches, stale-report rejection, "
            "threshold exit, LCOV/Cobertura imports, and dashboard HTTP"
        )
        return reports


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("sample", type=Path)
    parser.add_argument("--browser", action="store_true")
    args = parser.parse_args()
    verify(args.sample.resolve(), args.browser)
