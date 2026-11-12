"""Explicit local test execution. Importing reports never executes repository code."""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

from coverage_lab.model import CoverageError
from coverage_lab.reports import load_report


def _run(command: list[str], repo: Path, env: dict, timeout: int) -> None:
    print(f"Running in {repo}: {subprocess.list2cmdline(command)}", file=sys.stderr)
    try:
        subprocess.run(
            command,
            cwd=repo,
            env=env,
            timeout=timeout,
            check=True,
            stdout=sys.stderr,
            stderr=sys.stderr,
        )
    except subprocess.TimeoutExpired as error:
        raise CoverageError(f"Test command exceeded {timeout} seconds.") from error
    except subprocess.CalledProcessError as error:
        raise CoverageError(
            f"Test command failed with exit code {error.returncode}; no coverage success reported."
        ) from error
    except FileNotFoundError as error:
        raise CoverageError(f"Required executable not found: {command[0]}") from error


def detect_runner(repo: Path) -> str:
    python_markers = ("pyproject.toml", "setup.py", "pytest.ini", "setup.cfg")
    python = any((repo / file).exists() for file in python_markers) or any(repo.glob("*.py"))
    javascript = (repo / "package.json").is_file()
    if python and javascript:
        raise CoverageError("Multiple toolchains detected; choose --runner python or npm.")
    if python:
        return "python"
    if javascript:
        return "npm"
    raise CoverageError(
        "No supported test runner detected. Import an LCOV/Cobertura/coverage.py report."
    )


@contextmanager
def github_checkout(url: str, ref: str | None = None, timeout: int = 300):
    match = re.fullmatch(
        r"https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?", url
    )
    if not match or match[1] in {".", ".."} or match[2] in {".", ".."}:
        raise CoverageError(
            "Use an HTTPS GitHub repository URL without credentials or query parameters."
        )
    if ref and ref.startswith("-"):
        raise CoverageError("Git ref cannot begin with '-'.")
    with tempfile.TemporaryDirectory(prefix="coverage-lab-clone-") as directory:
        destination = Path(directory) / "repository"
        command = ["git", "clone", "--depth", "1"]
        if ref:
            command += ["--branch", ref]
        command += ["--", url, str(destination)]
        env = {
            key: value for key, value in os.environ.items() if not key.startswith("COVERAGE_LAB_")
        }
        env["GIT_TERMINAL_PROMPT"] = "0"
        _run(command, Path(directory), env, timeout)
        yield destination


def measure(
    repo: Path,
    runner: str = "auto",
    framework: str = "auto",
    timeout: int = 300,
    python_executable: str | None = None,
) -> dict:
    repo = repo.resolve()
    if not repo.is_dir():
        raise CoverageError(f"Repository directory does not exist: {repo}")
    if timeout < 1:
        raise CoverageError("Timeout must be positive.")
    if runner == "auto":
        runner = detect_runner(repo)
    # Do not pass the analyzer's AI credential to the repository's tests.
    env = {key: value for key, value in os.environ.items() if not key.startswith("COVERAGE_LAB_")}
    with tempfile.TemporaryDirectory(prefix="coverage-lab-") as directory:
        output = Path(directory)
        if runner == "python":
            executable = python_executable or sys.executable
            if framework == "auto":
                framework = (
                    "pytest"
                    if (repo / "pytest.ini").exists()
                    or (repo / "conftest.py").exists()
                    or any((repo / "tests").glob("conftest.py"))
                    or (
                        (repo / "pyproject.toml").exists()
                        and "[tool.pytest" in (repo / "pyproject.toml").read_text(encoding="utf-8")
                    )
                    else "unittest"
                )
            env["COVERAGE_FILE"] = str(output / ".coverage")
            command = [
                executable,
                "-m",
                "coverage",
                "run",
                "--branch",
                "--source=.",
                "--omit=tests/*,*/tests/*,test_*.py,*/test_*.py,.venv/*,venv/*",
                "-m",
            ]
            if framework == "pytest":
                command += ["pytest"]
            else:
                command += [
                    "unittest",
                    "discover",
                    "-s",
                    "tests" if (repo / "tests").is_dir() else ".",
                ]
            _run(command, repo, env, timeout)
            report_path = output / "coverage.json"
            _run([executable, "-m", "coverage", "json", "-o", str(report_path)], repo, env, timeout)
        elif runner == "npm":
            try:
                package = json.loads((repo / "package.json").read_text(encoding="utf-8"))
            except json.JSONDecodeError as error:
                raise CoverageError("package.json is not valid JSON.") from error
            if not isinstance(package, dict) or not isinstance(package.get("scripts"), dict):
                raise CoverageError("package.json needs a scripts object containing coverage.")
            if not isinstance(package["scripts"].get("coverage"), str):
                raise CoverageError(
                    "package.json needs a coverage script that writes coverage/lcov.info."
                )
            report_path = repo / "coverage" / "lcov.info"
            # Never mistake an old successful report for the current run.
            if report_path.exists():
                raise CoverageError(
                    "coverage/lcov.info already exists. Move/remove that exact report before running "
                    "again, or import it with 'coverage-lab report'."
                )
            npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
            if npm is None:
                raise CoverageError("npm is required for JavaScript/TypeScript coverage.")
            _run([npm, "run", "coverage"], repo, env, timeout)
            if not report_path.is_file():
                raise CoverageError("Coverage script did not create coverage/lcov.info.")
        else:
            raise CoverageError(f"Unsupported runner: {runner}")
        report = load_report(report_path, repo).to_dict()
        report["measurement"] = {"runner": runner, "repository": str(repo), "tests_passed": True}
        return report
