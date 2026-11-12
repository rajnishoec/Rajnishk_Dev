"""Language-independent coverage model; unknown coverage is never called 100%."""

from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath


class CoverageError(Exception):
    """An input, measurement, or provider error safe to display to the user."""


def percentage(covered: int, total: int) -> float | None:
    return round(100 * covered / total, 2) if total else None


def display_path(value: str, root: Path | None) -> str:
    value = value.strip().replace("\\", "/")
    if not value:
        raise CoverageError("Coverage file has an empty source path.")
    if root is not None and Path(value).is_absolute():
        try:
            return Path(value).resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            pass
    return str(PurePosixPath(value))


@dataclass
class FileCoverage:
    path: str
    hits: dict[int, int] = field(default_factory=dict)
    branches: dict[int, tuple[int, int]] = field(default_factory=dict)

    def add_line(self, number: int, hits: int) -> None:
        if number < 1 or hits < 0:
            raise CoverageError(f"Invalid line number or hit count in {self.path}.")
        self.hits[number] = max(hits, self.hits.get(number, 0))

    def add_branches(self, line: int, covered: int, total: int) -> None:
        if line < 1 or covered < 0 or total < covered:
            raise CoverageError(f"Invalid branch counts in {self.path}.")
        previous = self.branches.get(line, (0, 0))
        self.branches[line] = (max(covered, previous[0]), max(total, previous[1]))

    def to_dict(self) -> dict:
        covered = sum(value > 0 for value in self.hits.values())
        branch_covered = sum(value[0] for value in self.branches.values())
        branch_total = sum(value[1] for value in self.branches.values())
        return {
            "path": self.path,
            "lines": {
                "covered": covered,
                "total": len(self.hits),
                "percent": percentage(covered, len(self.hits)),
            },
            "branches": {
                "covered": branch_covered,
                "total": branch_total,
                "percent": percentage(branch_covered, branch_total),
            },
            "missing_lines": sorted(line for line, count in self.hits.items() if not count),
            "partial_branch_lines": sorted(
                line for line, (hit, total) in self.branches.items() if hit < total
            ),
            "line_hits": {str(line): hits for line, hits in sorted(self.hits.items())},
            "branch_counts": {
                str(line): list(counts) for line, counts in sorted(self.branches.items())
            },
        }


@dataclass
class Report:
    files: list[FileCoverage]
    format: str

    def to_dict(self) -> dict:
        files = [file.to_dict() for file in sorted(self.files, key=lambda item: item.path)]
        if not files or not any(file["lines"]["total"] for file in files):
            raise CoverageError("Report contains no executable lines; coverage is unknown.")
        totals = {}
        for kind in ("lines", "branches"):
            covered = sum(file[kind]["covered"] for file in files)
            total = sum(file[kind]["total"] for file in files)
            totals[kind] = {
                "covered": covered,
                "total": total,
                "percent": percentage(covered, total),
            }
        return {
            "schema_version": 1,
            "format": self.format,
            "totals": totals,
            "files": files,
            "limitations": [
                "Coverage measures executed code, not assertion quality or correctness.",
                "Only source files included by the test runner appear in this report.",
                "Unknown or unreported branch coverage is null, not 100%.",
            ],
        }


def prioritize(report: dict, limit: int = 12) -> list[dict]:
    ranked = sorted(
        report["files"],
        key=lambda file: (
            -len(file["missing_lines"]),
            -len(file["partial_branch_lines"]),
            file["path"],
        ),
    )
    return [
        {
            "path": file["path"],
            "missing_lines": file["missing_lines"],
            "partial_branch_lines": file["partial_branch_lines"],
            "line_percent": file["lines"]["percent"],
        }
        for file in ranked
        if file["missing_lines"] or file["partial_branch_lines"]
    ][:limit]
