"""Import LCOV, Cobertura XML, and coverage.py JSON without guessing coverage."""

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath

from coverage_lab.model import CoverageError, FileCoverage, Report, display_path

MAX_REPORT_BYTES = 25 * 1024 * 1024


def parse_report(text: str, root: Path | None = None) -> Report:
    if len(text.encode("utf-8")) > MAX_REPORT_BYTES:
        raise CoverageError("Coverage report exceeds the 25 MiB limit.")
    try:
        stripped = text.lstrip("\ufeff \r\n\t")
        if stripped.startswith("{"):
            data = json.loads(stripped)
            result = (
                _normalized(data, root)
                if data.get("schema_version") == 1
                else _coverage_json(data, root)
            )
        elif stripped.startswith("<"):
            if re.search(r"<!DOCTYPE|<!ENTITY", stripped, re.IGNORECASE):
                raise CoverageError("XML DTDs and entities are not permitted.")
            result = _cobertura(ET.fromstring(stripped), root)
        else:
            result = _lcov(stripped, root)
        result.to_dict()
        return result
    except (ValueError, KeyError, TypeError, AttributeError, IndexError, ET.ParseError) as error:
        raise CoverageError(f"Invalid coverage report: {error}") from error


def load_report(path: Path, root: Path | None = None) -> Report:
    if path.stat().st_size > MAX_REPORT_BYTES:
        raise CoverageError("Coverage report exceeds the 25 MiB limit.")
    return parse_report(path.read_text(encoding="utf-8-sig"), root)


def _normalized(data: dict, root: Path | None) -> Report:
    files = []
    seen = set()
    for entry in data["files"]:
        file = FileCoverage(display_path(entry["path"], root))
        if file.path in seen:
            raise CoverageError("Normalized report contains duplicate file paths.")
        seen.add(file.path)
        for line, hits in entry["line_hits"].items():
            file.add_line(int(line), int(hits))
        for line, (covered, total) in entry["branch_counts"].items():
            file.add_branches(int(line), int(covered), int(total))
        files.append(file)
    return Report(files, "coverage-lab")


def _coverage_json(data: dict, root: Path | None) -> Report:
    if not isinstance(data.get("files"), dict):
        raise CoverageError("Expected coverage.py JSON with a 'files' object.")
    files = []
    for path, entry in data["files"].items():
        file = FileCoverage(display_path(path, root))
        for line in entry.get("missing_lines", []):
            file.add_line(int(line), 0)
        for line in entry["executed_lines"]:
            file.add_line(int(line), 1)
        branches: dict[int, dict[int, bool]] = {}
        for key, covered in (("missing_branches", False), ("executed_branches", True)):
            for source, target in entry.get(key, []):
                source, target = int(source), int(target)
                branches.setdefault(source, {})[target] = (
                    branches.get(source, {}).get(target, False) or covered
                )
        for line, edges in branches.items():
            file.add_branches(line, sum(edges.values()), len(edges))
        files.append(file)
    return Report(files, "coverage.py")


def _lcov(text: str, root: Path | None) -> Report:
    files: dict[str, FileCoverage] = {}
    branch_hits: dict[str, dict[tuple[int, str, str], bool]] = {}
    current: FileCoverage | None = None
    for row in text.splitlines():
        row = row.strip()
        if row.startswith("SF:"):
            path = display_path(row[3:], root)
            current = files.setdefault(path, FileCoverage(path))
            branch_hits.setdefault(path, {})
        elif row == "end_of_record":
            current = None
        elif row.startswith(("DA:", "BRDA:")):
            if current is None:
                raise CoverageError("LCOV line/branch record appears before an SF record.")
            values = row.split(":", 1)[1].split(",")
            if row.startswith("DA:"):
                current.add_line(int(values[0]), int(values[1]))
            else:
                line, block, branch, taken = values
                key = (int(line), block, branch)
                hit = False if taken == "-" else int(taken) > 0
                branch_hits[current.path][key] = branch_hits[current.path].get(key, False) or hit
    for path, entries in branch_hits.items():
        by_line: dict[int, list[bool]] = {}
        for (line, _block, _branch), hit in entries.items():
            by_line.setdefault(line, []).append(hit)
        for line, hits in by_line.items():
            files[path].add_branches(line, sum(hits), len(hits))
    return Report(list(files.values()), "lcov")


def _cobertura(document: ET.Element, root: Path | None) -> Report:
    if document.tag != "coverage":
        raise CoverageError("Expected a Cobertura <coverage> document.")
    files: dict[str, FileCoverage] = {}
    sources = [element.text for element in document.findall("./sources/source") if element.text]
    for item in document.findall(".//class"):
        filename = item.attrib["filename"]
        if root and not Path(filename).is_absolute():
            # coverage.py can make filenames relative to its <source>, not the repo.
            if not (root / filename).is_file():
                for source in sources:
                    candidate = Path(source) / filename
                    try:
                        candidate.resolve().relative_to(root.resolve())
                    except ValueError:
                        continue
                    if candidate.is_file():
                        filename = candidate.as_posix()
                        break
        path = display_path(str(PurePosixPath(filename.replace("\\", "/"))), root)
        file = files.setdefault(path, FileCoverage(path))
        for line in item.findall("./lines/line"):
            number = int(line.attrib["number"])
            file.add_line(number, int(line.attrib["hits"]))
            condition = line.get("condition-coverage")
            if condition:
                match = re.fullmatch(r"[\d.]+%\s*\((\d+)/(\d+)\)", condition)
                if not match:
                    raise CoverageError(f"Invalid Cobertura condition coverage: {condition}")
                file.add_branches(number, int(match[1]), int(match[2]))
    return Report(list(files.values()), "cobertura")
