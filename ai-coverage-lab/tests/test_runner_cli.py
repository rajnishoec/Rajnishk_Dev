import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from coverage_lab.cli import main
from coverage_lab.model import CoverageError
from coverage_lab.runner import _run, detect_runner, github_checkout, measure
from tests import LCOV, sample_report


class RunnerTests(unittest.TestCase):
    def test_detection_requires_explicit_choice_for_mixed_repositories(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(CoverageError):
                detect_runner(root)
            (root / "app.py").touch()
            self.assertEqual(detect_runner(root), "python")
            (root / "package.json").write_text("{}")
            with self.assertRaisesRegex(CoverageError, "Multiple"):
                detect_runner(root)
            (root / "app.py").unlink()
            self.assertEqual(detect_runner(root), "npm")

    def test_invalid_repository_and_timeout(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(CoverageError):
                measure(Path(directory) / "missing")
            with self.assertRaises(CoverageError):
                measure(Path(directory), timeout=0)

    @patch("coverage_lab.runner.subprocess.run")
    def test_subprocess_failure_timeout_and_missing_executable(self, run):
        for error in (
            subprocess.CalledProcessError(1, ["test"]),
            subprocess.TimeoutExpired(["test"], 1),
            FileNotFoundError(),
        ):
            run.side_effect = error
            with self.assertRaises(CoverageError):
                _run(["test"], Path("."), {}, 1)

    def test_invalid_github_urls_and_option_like_refs_are_rejected(self):
        for url in (
            "file:///tmp/x",
            "https://evil.example/x/y",
            "https://github.com/x/y?q=1",
            "https://token@github.com/x/y",
            "https://github.com/x/..",
        ):
            with self.assertRaises(CoverageError), github_checkout(url):
                self.fail("Invalid URL accepted")
        with (
            self.assertRaises(CoverageError),
            github_checkout("https://github.com/test/repo", "-bad"),
        ):
            self.fail("Invalid ref accepted")

    @patch("coverage_lab.runner._run")
    def test_github_clone_has_no_ai_credentials_and_cleans_temp_checkout(self, run):
        with patch.dict("os.environ", {"COVERAGE_LAB_API_KEY": "not-real"}):
            with github_checkout("https://github.com/test/repo", "main") as root:
                self.assertEqual(root.name, "repository")
                command, parent, env, timeout = run.call_args.args
                self.assertIn("--branch", command)
                self.assertNotIn("COVERAGE_LAB_API_KEY", env)
                self.assertTrue(parent.exists())
            self.assertFalse(parent.exists())

    def test_npm_missing_script_and_stale_report_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "package.json").write_text("{}")
            with self.assertRaisesRegex(CoverageError, "scripts object"):
                measure(root, "npm")
            (root / "package.json").write_text('{"scripts":{"coverage":"do something"}}')
            (root / "coverage").mkdir()
            (root / "coverage" / "lcov.info").write_text(LCOV)
            with self.assertRaisesRegex(CoverageError, "already exists"):
                measure(root, "npm")

    def test_invalid_npm_manifests_fail_without_traceback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for value in ("{", "[]", '{"scripts":[]}', '{"scripts":{"coverage":null}}'):
                (root / "package.json").write_text(value)
                with self.subTest(value=value), self.assertRaises(CoverageError):
                    measure(root, "npm")

    @patch("coverage_lab.runner._run")
    @patch("coverage_lab.runner.shutil.which", return_value="npm")
    def test_npm_missing_output_is_not_success(self, which, run):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "package.json").write_text('{"scripts":{"coverage":"test"}}')
            with self.assertRaisesRegex(CoverageError, "did not create"):
                measure(root, "npm")
        which.return_value = None
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "package.json").write_text('{"scripts":{"coverage":"test"}}')
            with self.assertRaisesRegex(CoverageError, "npm is required"):
                measure(root, "npm")

    @patch("coverage_lab.runner._run")
    def test_python_framework_selection_and_ai_key_stripping(self, run):
        def fake_run(command, repo, env, timeout):
            self.assertNotIn("COVERAGE_LAB_API_KEY", env)
            if "json" in command:
                Path(command[-1]).write_text(
                    json.dumps({"files": {"app.py": {"executed_lines": [1], "missing_lines": [2]}}})
                )

        run.side_effect = fake_run
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "pyproject.toml").write_text("[tool.pytest.ini_options]\n")
            with patch.dict("os.environ", {"COVERAGE_LAB_API_KEY": "not-real"}):
                result = measure(root, "python", python_executable="target-python")
            command = run.call_args_list[0].args[0]
            self.assertEqual(command[0], "target-python")
            self.assertEqual(command[-1], "pytest")
            self.assertEqual(result["totals"]["lines"]["percent"], 50)


class CLITests(unittest.TestCase):
    def test_report_output_roundtrip_and_threshold_exit_codes(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "lcov.info"
            output = Path(directory) / "result.json"
            report.write_text(LCOV)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["report", str(report), "--output", str(output)]), 0)
                self.assertEqual(main(["report", str(report), "--fail-under", "80"]), 2)
                self.assertEqual(main(["report", str(output), "--fail-under", "60"]), 0)
            self.assertEqual(json.loads(output.read_text())["totals"]["lines"]["percent"], 66.67)

    def test_bad_arguments_and_missing_report_fail(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["report", "missing.info"]), 1)
            self.assertEqual(main(["report", "missing.info", "--fail-under", "101"]), 1)
            self.assertEqual(main(["report", "missing.info", "--include-source"]), 1)

    @patch("coverage_lab.cli.measure", return_value=sample_report())
    @patch("coverage_lab.cli.analyze", return_value={"summary": "test", "recommendations": []})
    def test_run_routes_measurement_and_optional_ai(self, analyze, measure):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["run", ".", "--runner", "python", "--ai"]), 0)
        self.assertIn("ai", json.loads(output.getvalue()))
        analyze.assert_called_once()

    @patch("coverage_lab.cli.github_checkout")
    @patch("coverage_lab.cli.measure", return_value=sample_report() | {"measurement": {}})
    def test_scan_outputs_github_url_not_deleted_temporary_path(self, measure, checkout):
        checkout.return_value.__enter__.return_value = Path(".")
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["scan", "https://github.com/test/repo"]), 0)
        self.assertEqual(
            json.loads(output.getvalue())["measurement"]["repository"],
            "https://github.com/test/repo",
        )
