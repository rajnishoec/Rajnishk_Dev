# Coverage Lab

**Real coverage. Grounded AI recommendations. No invented percentages.**

A local-first CLI and browser dashboard that measure Python and JavaScript/TypeScript
test coverage, import reports from other toolchains, and use an optional AI provider
to recommend tests for *measured* gaps.

![CI](https://github.com/rajnishoec/Rajnishk_Dev/actions/workflows/coverage-lab.yml/badge.svg)

## What it does

- **Measure:** run Python `unittest`/`pytest` with coverage.py, or an npm coverage script.
- **Scan GitHub:** temporarily clone a trusted GitHub repository and measure its tests.
- **Import:** LCOV, Cobertura XML, coverage.py JSON, and normalized Coverage Lab JSON.
- **Understand:** line/branch totals, uncovered lines, partial branches, and file priorities.
- **Ask AI:** propose test scenarios using only measured gaps; reject invented paths/line anchors.
- **Gate CI:** fail below a configurable line-coverage threshold.
- **Inspect:** local dashboard, report upload, JSON export, responsive file breakdown.

Coverage is evidence of execution, **not** proof of correctness or assertion quality.
Only files included by the underlying runner are measured. Unknown branch coverage
is `null`/N/A, not 100%. Different tools count executable lines and branches differently.

## Quick start

Python 3.11+ is required. JavaScript coverage additionally requires Node.js and npm.

```powershell
git clone https://github.com/rajnishoec/Rajnishk_Dev.git
cd Rajnishk_Dev\ai-coverage-lab
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install .
coverage-lab --help
```

On macOS/Linux activate with `source .venv/bin/activate`. All commands below also
work as `python -m coverage_lab`.

### Try the companion repository

The [sample project](../ai-coverage-sample/) has small,
intentionally under-tested Python and JavaScript applications. Its tests pass, but
its validation, refund, discount and international-shipping branches are not all covered.

```powershell
coverage-lab run ..\ai-coverage-sample --runner python --output python-report.json
coverage-lab run ..\ai-coverage-sample --runner npm --output js-report.json
coverage-lab serve
```

Open **http://127.0.0.1:8765**, then upload either generated JSON file.

Both projects live in this public repository; cloning does not require authentication.
For other multi-project repositories, clone first and use `run` on the relevant
subdirectory. `scan` measures a repository's root.

`scan` and `run` **execute repository code with your account's permissions**, not in a
sandbox. Run them only for repositories you trust. GitHub scanning does not install
target dependencies or submodules. For projects requiring setup, clone and install
their documented dependencies in an isolated environment, then use `run`.

### Analyze your own repository

```powershell
coverage-lab run C:\src\my-python-repo --runner python --framework pytest --python C:\src\my-python-repo\.venv\Scripts\python.exe --output report.json
coverage-lab run C:\src\my-js-repo --runner npm --output report.json
coverage-lab report C:\src\my-repo\coverage\lcov.info --repo C:\src\my-repo --fail-under 80
coverage-lab report C:\src\my-repo\coverage.xml
coverage-lab scan https://github.com/OWNER/REPO --ref main --runner python
```

Python auto-detection selects pytest for `pytest.ini`, a root/tests `conftest.py`,
or a `[tool.pytest...]` configuration; otherwise it selects unittest. Override
`--framework` when necessary. Your target interpreter must have `coverage` and its
own dependencies, including pytest when selected. The Python adapter includes
unexecuted importable source modules through `--source=.` and omits conventional
test and virtual-environment directories. Customize coverage scope in the target
project; files the runner does not discover cannot be inferred.

For JavaScript/TypeScript, provide a `coverage` npm script that exits nonzero on
failed tests and writes **`coverage/lcov.info`** (e.g. Vitest/Jest with LCOV output).
Coverage Lab does not transpile TypeScript or install packages. It intentionally
rejects an existing LCOV output before execution to avoid reusing stale evidence;
move/delete that **specific report** before rerunning, or import it directly.
Mixed-toolchain repositories require an explicit `--runner`.

Other languages are supported through **report import**, not automatic execution:
use Coverlet/.NET or JaCoCo's Cobertura conversion, Go-to-LCOV tooling, or another
compatible exporter. A repository with no tests/reports cannot have coverage measured
by AI alone.

### Configure real AI

AI is off by default. Set an OpenAI-compatible **base URL**, model/deployment ID,
and API key in the process environment:

```powershell
$env:COVERAGE_LAB_ENDPOINT = "https://api.openai.com/v1"
$env:COVERAGE_LAB_MODEL = "YOUR_AVAILABLE_MODEL"
$env:COVERAGE_LAB_API_KEY = "YOUR_API_KEY"
coverage-lab report report.json --ai --output report-with-ai.json
```

For an Azure AI Foundry deployment exposing the OpenAI-compatible v1 endpoint:

```powershell
$env:COVERAGE_LAB_ENDPOINT = "https://YOUR_RESOURCE.openai.azure.com/openai/v1"
$env:COVERAGE_LAB_MODEL = "YOUR_DEPLOYMENT_NAME"
```

The chosen deployment must support chat completions, bearer API-key authentication
and JSON-object response format. Legacy Azure `api-version`/`api-key` endpoints are
not supported. Provider access, quota and billing are your responsibility.

By default, **only coverage totals, file paths and gap line numbers are sent**.
CLI `--ai --include-source --repo YOUR_REPO` explicitly opts into bounded source
excerpts (at most 16,000 characters, 4,000 per file). Source paths are confined to
that repository, including symlink resolution. Review your provider/data policies
before opting in. The dashboard never reads source files or runs test commands.
Keys stay in environment variables and are stripped from child test processes.

AI output is separately labeled as unverified. It cannot change measured metrics.
Missing credentials, provider failures and malformed/unanchored suggestions fail
explicitly rather than producing fake AI results. The HTTP contract is tested with
test doubles; **a live provider requires your own configuration**.

GitHub Models is not used: its inference service was
[retired on July 30, 2026](https://docs.github.com/en/github-models).

## CI and exit codes

```yaml
- uses: actions/setup-python@v5
  with:
    python-version: "3.12"
- run: python -m pip install . coverage
- run: coverage-lab report coverage.xml --fail-under 80 --output coverage-summary.json
```

Generate `coverage.xml` with your own test runner before the last step. Alternatively,
install Coverage Lab alongside your project's test dependencies and use `run`.

| Code | Meaning |
| --- | --- |
| `0` | Measurement/import succeeded and the requested threshold passed |
| `1` | Invalid input, failed/timed-out tests, missing tool, or AI/provider error |
| `2` | Successful measurement below `--fail-under` |
| `130` | Interrupted |

`--timeout` defaults to 300 seconds per command. JSON goes to stdout; test-runner
logs go to stderr. `--output` writes a persistent report; its parent must exist.
Threshold failure still writes the measured report for diagnosis.

## Development and E2E verification

```powershell
python -m pip install -e ".[dev]"
python -m ruff check .
python -m ruff format --check .
python -m coverage run -m unittest discover -s tests -v
python -m coverage report
python scripts\e2e.py ..\ai-coverage-sample --browser
```

On Windows the browser test uses installed Microsoft Edge in an isolated temporary
browser context. On Linux/macOS install Chromium first with
`python -m playwright install --with-deps chromium`.

E2E verification copies the sample into a temporary directory, runs **both actual
test toolchains**, checks missing lines/branches, threshold failure, stale npm report
rejection, LCOV/Cobertura import, dashboard HTTP upload and optional browser rendering.
Browser mode checks desktop results, mobile overflow and JavaScript errors, and saves
an ignored screenshot to `artifacts/dashboard.png`. CI runs the unit suite across
Windows/Linux and Python 3.11/3.14, then an independent browser E2E job. Both
workflows live in the parent repository's `.github/workflows` directory and use
the sibling sample folder from the same checkout.

## Architecture

```text
local repo / trusted GitHub clone --> real test runner --> coverage report
LCOV / Cobertura / coverage.py JSON --------------------> normalized measured model
                                                             |
                                            CLI JSON + dashboard + CI threshold
                                                             |
                                          opt-in OpenAI-compatible recommendations
```

The dashboard binds only to loopback, uses per-session upload tokens, rejects
cross-origin/DNS-rebinding requests, caps report size and disables XML DTD/entities.
Uploaded text and AI responses render as text, not executable HTML. This is a local
development application, not a hosted multi-tenant code-execution service.

MIT licensed. Contributions and additional report adapters are welcome.
