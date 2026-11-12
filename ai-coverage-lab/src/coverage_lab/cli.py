import argparse
import json
import sys
from pathlib import Path

from coverage_lab import __version__
from coverage_lab.ai import analyze
from coverage_lab.model import CoverageError, prioritize
from coverage_lab.reports import load_report
from coverage_lab.runner import github_checkout, measure


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--output", type=Path, help="Write normalized JSON (parent must exist).")
    parser.add_argument(
        "--fail-under", type=float, help="Exit 2 if measured line coverage is lower."
    )
    parser.add_argument(
        "--ai", action="store_true", help="Send measured gaps to the configured AI provider."
    )
    parser.add_argument(
        "--include-source",
        action="store_true",
        help="Explicitly allow bounded source excerpts to be sent to the AI provider.",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Measure coverage, then use AI to prioritize real gaps."
    )
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    report = commands.add_parser(
        "report", help="Import a report without executing repository code."
    )
    report.add_argument("file", type=Path)
    report.add_argument(
        "--repo", type=Path, help="Source root for relative paths and optional excerpts."
    )
    _common(report)
    run = commands.add_parser("run", help="Execute tests in a local repository you trust.")
    run.add_argument("repo", type=Path)
    run.add_argument("--runner", choices=("auto", "python", "npm"), default="auto")
    run.add_argument("--framework", choices=("auto", "unittest", "pytest"), default="auto")
    run.add_argument(
        "--python", help="Target Python interpreter with project dependencies and coverage."
    )
    run.add_argument("--timeout", type=int, default=300)
    _common(run)
    scan = commands.add_parser(
        "scan", help="Clone a trusted GitHub repo temporarily and run its tests."
    )
    scan.add_argument("url")
    scan.add_argument("--ref", help="Branch or tag to clone.")
    scan.add_argument("--runner", choices=("auto", "python", "npm"), default="auto")
    scan.add_argument("--framework", choices=("auto", "unittest", "pytest"), default="auto")
    scan.add_argument(
        "--python", help="Python interpreter containing target dependencies and coverage."
    )
    scan.add_argument("--timeout", type=int, default=300)
    _common(scan)
    serve = commands.add_parser("serve", help="Open the loopback-only report dashboard.")
    serve.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    try:
        if args.command == "serve":
            from coverage_lab.server import serve_dashboard

            serve_dashboard(args.port)
            return 0
        if args.fail_under is not None and not 0 <= args.fail_under <= 100:
            raise CoverageError("--fail-under must be between 0 and 100.")
        if args.include_source and not args.ai:
            raise CoverageError("--include-source requires --ai.")
        if args.command == "scan":
            with github_checkout(args.url, args.ref, args.timeout) as root:
                data = measure(root, args.runner, args.framework, args.timeout, args.python)
                if args.ai:
                    data["ai"] = analyze(data, root, args.include_source)
            data["measurement"]["repository"] = args.url
            data["priorities"] = prioritize(data)
            encoded = json.dumps(data, indent=2)
            if args.output:
                args.output.write_text(encoded + "\n", encoding="utf-8")
            print(encoded)
            if args.fail_under is not None and data["totals"]["lines"]["percent"] < args.fail_under:
                return 2
            return 0
        if args.command == "run":
            data = measure(args.repo, args.runner, args.framework, args.timeout, args.python)
            root = args.repo
        else:
            data = load_report(args.file, args.repo).to_dict()
            root = args.repo
        data["priorities"] = prioritize(data)
        if args.ai:
            data["ai"] = analyze(data, root, args.include_source)
        encoded = json.dumps(data, indent=2)
        if args.output:
            args.output.write_text(encoded + "\n", encoding="utf-8")
        print(encoded)
        if args.fail_under is not None and data["totals"]["lines"]["percent"] < args.fail_under:
            return 2
        return 0
    except (CoverageError, OSError, ValueError) as error:
        print(f"coverage-lab: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
