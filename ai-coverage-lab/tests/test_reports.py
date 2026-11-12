import json
import tempfile
import unittest
from pathlib import Path

from coverage_lab.model import CoverageError, FileCoverage, display_path, percentage, prioritize
from coverage_lab.reports import load_report, parse_report
from tests import LCOV, sample_report


class ReportTests(unittest.TestCase):
    def test_lcov_counts_lines_and_real_branch_edges(self):
        data = sample_report()
        self.assertEqual(data["totals"]["lines"], {"covered": 2, "total": 3, "percent": 66.67})
        self.assertEqual(data["totals"]["branches"]["percent"], 50)
        self.assertEqual(data["files"][0]["missing_lines"], [2])
        self.assertEqual(data["files"][0]["partial_branch_lines"], [2])

    def test_lcov_repeated_records_merge_edges_and_lines_without_double_counting(self):
        extra = "SF:app.py\nDA:2,1\nBRDA:2,0,1,1\nend_of_record\n"
        data = parse_report(LCOV + extra).to_dict()
        self.assertEqual(data["totals"]["lines"]["percent"], 100)
        self.assertEqual(data["totals"]["branches"]["total"], 2)
        self.assertEqual(data["totals"]["branches"]["percent"], 100)

    def test_coverage_json_preserves_unexecuted_files_and_edges(self):
        raw = {
            "files": {
                "app.py": {
                    "executed_lines": [1],
                    "missing_lines": [2, 3],
                    "executed_branches": [[1, 2]],
                    "missing_branches": [[1, 3]],
                },
                "unused.py": {"executed_lines": [], "missing_lines": [1, 2]},
            }
        }
        data = parse_report(json.dumps(raw)).to_dict()
        self.assertEqual(data["totals"]["lines"]["percent"], 20)
        self.assertEqual(data["totals"]["branches"]["percent"], 50)
        self.assertEqual(len(data["files"]), 2)

    def test_cobertura_counts_class_lines_not_method_duplicates(self):
        xml = """<coverage><packages><package><classes><class filename="app.cs">
        <methods><method><lines><line number="1" hits="1"/></lines></method></methods>
        <lines><line number="1" hits="1"/><line number="2" hits="0" branch="true"
        condition-coverage="50% (1/2)"/></lines></class></classes></package></packages></coverage>"""
        data = parse_report(xml).to_dict()
        self.assertEqual(data["totals"]["lines"]["total"], 2)
        self.assertEqual(data["totals"]["branches"]["percent"], 50)

    def test_cobertura_resolves_source_directory_within_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src").mkdir()
            (root / "src" / "app.py").write_text("pass\n")
            xml = f"""<coverage><sources><source>{(root / "src").as_posix()}</source></sources>
            <packages><package><classes><class filename="app.py"><lines>
            <line number="1" hits="1"/></lines></class></classes></package></packages></coverage>"""
            self.assertEqual(parse_report(xml, root).files[0].path, "src/app.py")

    def test_branch_coverage_is_unknown_when_not_reported(self):
        data = parse_report("SF:main.go\nDA:1,0\nend_of_record\n").to_dict()
        self.assertIsNone(data["totals"]["branches"]["percent"])
        self.assertEqual(data["totals"]["lines"]["percent"], 0)
        self.assertIsNone(percentage(0, 0))

    def test_normalized_round_trip_recomputes_totals(self):
        data = sample_report()
        data["totals"]["lines"]["percent"] = 100
        decoded = parse_report(json.dumps(data)).to_dict()
        self.assertEqual(decoded["totals"]["lines"]["percent"], 66.67)
        self.assertEqual(decoded["files"][0]["missing_lines"], [2])

    def test_duplicate_normalized_files_are_rejected(self):
        data = sample_report()
        data["files"].append(data["files"][0])
        with self.assertRaises(CoverageError):
            parse_report(json.dumps(data))

    def test_malformed_and_empty_reports_fail_explicitly(self):
        for raw in (
            "",
            "SF:empty.py\nend_of_record",
            "DA:1,1",
            "SF:x\nDA:-1,1",
            "SF:x\nDA:1,-1",
            "SF:x\nDA:1",
            '{"files":[]}',
            "[]",
            "{",
            '<coverage><class filename="x"><lines><line number="1" hits="1" '
            'condition-coverage="nonsense"/></lines></class></coverage>',
            '<coverage><class filename="x"><lines><line number="1" hits="1" '
            'condition-coverage="100% (3/2)"/></lines></class></coverage>',
            '<!DOCTYPE coverage [<!ENTITY x "x">]><coverage/>',
            "<root/>",
            "<broken",
        ):
            with self.subTest(raw=raw), self.assertRaises(CoverageError):
                parse_report(raw)

    def test_file_loading_and_repository_relative_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report_path = root / "report.info"
            report_path.write_text(LCOV.replace("app.py", (root / "app.py").as_posix()))
            self.assertEqual(load_report(report_path, root).files[0].path, "app.py")
        self.assertEqual(display_path("src\\app.py", None), "src/app.py")
        with self.assertRaises(CoverageError):
            display_path("", None)

    def test_invalid_branch_and_line_counts_are_rejected(self):
        file = FileCoverage("app.py")
        for values in ((0, 1, 2), (1, -1, 2), (1, 3, 2)):
            with self.assertRaises(CoverageError):
                file.add_branches(*values)

    def test_priorities_rank_largest_measured_gaps(self):
        report = parse_report(LCOV + "SF:other.py\nDA:1,0\nDA:2,0\nend_of_record").to_dict()
        self.assertEqual(prioritize(report, 1)[0]["path"], "other.py")
