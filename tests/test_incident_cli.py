"""End-to-end tests of the extended offline CLI and its output contracts."""
import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from incident_cli import read_csv, read_jsonl, safe_write

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "incident_cli.py"


def sample_csv(values=None):
    values = [100] * 6 + [1000] if values is None else values
    return "service,latency_ms\n" + "".join(f"api,{value}\n" for value in values)


class IncidentCliTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.input = self.root / "latencies.csv"
        self.input.write_text(sample_csv(), encoding="utf-8")

    def invoke(self, *args):
        return subprocess.run(
            [sys.executable, str(CLI), str(self.input), *args],
            capture_output=True,
            text=True,
            cwd=ROOT,
            timeout=15,
        )

    def test_json_is_default_and_detects_anomaly(self):
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["accepted_rows"], 7)
        self.assertEqual(len(report["incidents"]), 1)
        self.assertEqual(report["incidents"][0]["service"], "api")

    def test_json_report_contains_summary(self):
        result = self.invoke()
        report = json.loads(result.stdout)
        self.assertEqual(report["services"]["api"]["samples"], 7)
        self.assertEqual(report["rejected_rows"], 0)
        self.assertEqual(report["schema_version"], 1)

    def test_summary_format_is_human_readable(self):
        result = self.invoke("--format", "summary")
        self.assertEqual(result.returncode, 0)
        self.assertIn("Latency incident analysis", result.stdout)
        self.assertIn("Critical: 1", result.stdout)

    def test_markdown_format_has_tables(self):
        result = self.invoke("--format", "markdown")
        self.assertEqual(result.returncode, 0)
        self.assertIn("| Service | Samples |", result.stdout)

    def test_sarif_format_has_row_location(self):
        result = self.invoke("--format", "sarif")
        self.assertEqual(result.returncode, 0)
        data = json.loads(result.stdout)
        finding = data["runs"][0]["results"][0]
        self.assertEqual(finding["ruleId"], "LATENCY-OUTLIER")
        self.assertEqual(finding["locations"][0]["physicalLocation"]["region"]["startLine"], 8)

    def test_critical_threshold_sets_exit_three(self):
        result = self.invoke("--fail-on", "critical")
        self.assertEqual(result.returncode, 3)

    def test_warning_threshold_sets_exit_three(self):
        result = self.invoke("--fail-on", "warning")
        self.assertEqual(result.returncode, 3)

    def test_none_threshold_never_fails(self):
        result = self.invoke("--fail-on", "none")
        self.assertEqual(result.returncode, 0)

    def test_no_incidents_does_not_fail(self):
        self.input.write_text(sample_csv([100] * 7), encoding="utf-8")
        result = self.invoke("--fail-on", "critical")
        self.assertEqual(result.returncode, 0)

    def test_service_filter_omits_other_services(self):
        result = self.invoke("--service", "db")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)["accepted_rows"], 0)

    def test_multiple_service_filters_are_supported(self):
        result = self.invoke("--service", "api", "--service", "db")
        self.assertEqual(json.loads(result.stdout)["accepted_rows"], 7)

    def test_zscore_method_is_selectable(self):
        result = self.invoke("--method", "zscore")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(len(json.loads(result.stdout)["incidents"]), 1)

    def test_iqr_method_is_selectable(self):
        result = self.invoke("--method", "iqr")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(len(json.loads(result.stdout)["incidents"]), 1)

    def test_invalid_method_is_rejected(self):
        result = self.invoke("--method", "magic")
        self.assertEqual(result.returncode, 2)

    def test_invalid_threshold_is_rejected(self):
        for threshold in ("0", "-1", "nan", "inf"):
            with self.subTest(threshold=threshold):
                result = self.invoke("--threshold", threshold)
                self.assertEqual(result.returncode, 2)
                self.assertNotIn("Traceback", result.stderr)

    def test_window_smaller_than_warmup_is_rejected(self):
        result = self.invoke("--window-size", "2", "--min-samples", "5")
        self.assertEqual(result.returncode, 2)
        self.assertIn("window_size", result.stderr)

    def test_invalid_cooldown_is_rejected(self):
        result = self.invoke("--cooldown-seconds", "-1")
        self.assertEqual(result.returncode, 2)

    def test_max_rows_limit_is_enforced(self):
        result = self.invoke("--max-rows", "3")
        self.assertEqual(result.returncode, 2)
        self.assertIn("maximum input", result.stderr)

    def test_missing_input_is_reported_without_traceback(self):
        self.input.unlink()
        result = self.invoke()
        self.assertEqual(result.returncode, 2)
        self.assertIn("existing regular file", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_csv_missing_required_columns_is_rejected(self):
        self.input.write_text("x,y\n1,2\n", encoding="utf-8")
        result = self.invoke()
        self.assertEqual(result.returncode, 2)
        self.assertIn("requires service and latency_ms", result.stderr)

    def test_duplicate_csv_headers_are_rejected(self):
        self.input.write_text("service,latency_ms,service\napi,100,db\n", encoding="utf-8")
        result = self.invoke()
        self.assertEqual(result.returncode, 2)
        self.assertIn("duplicate column names", result.stderr)

    def test_empty_csv_is_rejected(self):
        self.input.write_text("", encoding="utf-8")
        result = self.invoke()
        self.assertEqual(result.returncode, 2)
        self.assertIn("no header", result.stderr)

    def test_invalid_csv_row_is_rejected_in_strict_mode(self):
        self.input.write_text("service,latency_ms\napi,not-a-number\n", encoding="utf-8")
        result = self.invoke("--strict")
        self.assertEqual(result.returncode, 2)
        self.assertIn("row 1", result.stderr)

    def test_invalid_csv_row_is_counted_in_default_mode(self):
        self.input.write_text("service,latency_ms\napi,not-a-number\n", encoding="utf-8")
        result = self.invoke()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)["rejected_rows"], 1)

    def test_jsonl_mode_reads_events(self):
        self.input.write_text(
            "".join(json.dumps({"service": "api", "latency_ms": value}) + "\n"
                    for value in [100] * 6 + [1000]),
            encoding="utf-8",
        )
        result = self.invoke("--input-format", "jsonl")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(len(json.loads(result.stdout)["incidents"]), 1)

    def test_invalid_jsonl_is_counted(self):
        self.input.write_text('{"service": "api", "latency_ms": 100}\n{broken\n',
                              encoding="utf-8")
        result = self.invoke("--input-format", "jsonl")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)["rejected_rows"], 1)

    def test_jsonl_array_is_rejected(self):
        self.input.write_text('["not", "a", "mapping"]\n', encoding="utf-8")
        result = self.invoke("--input-format", "jsonl")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)["rejected_rows"], 1)

    def test_output_writes_json_without_stdout(self):
        output = self.root / "report.json"
        result = self.invoke("--output", str(output))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertEqual(len(json.loads(output.read_text())["incidents"]), 1)

    def test_output_can_be_replaced_atomically(self):
        output = self.root / "report.json"
        output.write_text("stale", encoding="utf-8")
        result = self.invoke("--output", str(output))
        self.assertEqual(result.returncode, 0)
        self.assertNotEqual(output.read_text(), "stale")

    def test_output_cannot_overwrite_input(self):
        original = self.input.read_text()
        result = self.invoke("--output", str(self.input))
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.input.read_text(), original)

    def test_output_parent_must_exist(self):
        result = self.invoke("--output", str(self.root / "missing" / "out.json"))
        self.assertEqual(result.returncode, 2)
        self.assertIn("parent directory", result.stderr)

    def test_reader_supports_utf8_bom(self):
        self.input.write_text(sample_csv(), encoding="utf-8-sig")
        self.assertEqual(len(list(read_csv(self.input))), 7)

    def test_jsonl_reader_preserves_line_numbers(self):
        self.input.write_text('{"service":"api","latency_ms":1}\n\n'
                              '{"service":"api","latency_ms":2}\n', encoding="utf-8")
        self.assertEqual(len(list(read_jsonl(self.input))), 3)

    def test_safe_write_is_atomic_and_utf8(self):
        destination = self.root / "report.md"
        safe_write(destination, "ação\n", self.input)
        self.assertEqual(destination.read_text(encoding="utf-8"), "ação\n")
        self.assertEqual(list(self.root.glob(".incident-*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
