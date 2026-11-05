import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from analyzer import analyze, analyze_report

SCRIPT = Path(__file__).resolve().parents[1] / "analyzer.py"


class IncidentReportTests(unittest.TestCase):
    def test_explains_baselines_and_keeps_existing_anomaly_results(self):
        rows = [
            *({'service': 'api', 'latency_ms': str(value)}
              for value in [100, 99, 101, 100, 101, 99, 1000]),
            {'service': 'web', 'latency_ms': '20'},
            {'service': 'web', 'latency_ms': '21'},
            {'service': 'api', 'latency_ms': 'nan'},
            {'service': 'api', 'latency_ms': '-12'},
            {'service': 'web', 'latency_ms': 'not-a-number'},
        ]
        report = analyze_report(rows, threshold=2.3, min_samples=6)

        self.assertEqual(report['total_rows'], 12)
        self.assertEqual(report['accepted_rows'], 9)
        self.assertEqual(report['ignored_rows'], 3)
        self.assertEqual(report['threshold'], 2.3)
        self.assertEqual(report['anomalies'], analyze(rows, threshold=2.3, min_samples=6))
        self.assertEqual(report['baselines'][0]['service'], 'api')
        self.assertEqual(report['baselines'][0]['samples'], 7)
        self.assertTrue(report['baselines'][0]['baseline_available'])
        self.assertEqual(report['baselines'][0]['anomalies'], 1)
        self.assertEqual(report['baselines'][1], {
            'service': 'web',
            'samples': 2,
            'baseline_available': False,
            'mean_ms': None,
            'stddev_ms': None,
            'anomalies': 0,
        })
        self.assertEqual(report['min_samples'], 6)

    def test_empty_input_has_no_baselines(self):
        self.assertEqual(analyze_report([], min_samples=2)['baselines'], [])
        with self.assertRaises(ValueError):
            analyze_report([], threshold=0)
        with self.assertRaises(ValueError):
            analyze_report([], min_samples=1)

    def test_cli_legacy_json_is_unchanged_and_report_is_opt_in(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'latencies.csv'
            with path.open('w', newline='', encoding='utf-8') as handle:
                writer = csv.writer(handle)
                writer.writerow(('service', 'latency_ms'))
                writer.writerows([('api', value) for value in (100, 99, 101, 100, 101, 99, 1000)])
                writer.writerow(('api', 'NaN'))
            basic = subprocess.run(
                [sys.executable, str(SCRIPT), str(path), '--threshold', '2.3'],
                capture_output=True, text=True
            )
            self.assertEqual(basic.returncode, 0, basic.stderr)
            self.assertEqual(list(json.loads(basic.stdout)), ['anomalies'])

            full = subprocess.run(
                [sys.executable, str(SCRIPT), str(path), '--threshold', '2.3', '--format', 'report'],
                capture_output=True, text=True
            )
            self.assertEqual(full.returncode, 0, full.stderr)
            report = json.loads(full.stdout)
            self.assertEqual(report['ignored_rows'], 1)
            self.assertEqual(report['baselines'][0]['anomalies'], 1)

            summary = subprocess.run(
                [sys.executable, str(SCRIPT), str(path), '--threshold', '2.3', '--format', 'summary'],
                capture_output=True, text=True
            )
            self.assertEqual(summary.returncode, 0, summary.stderr)
            self.assertIn('Ignored: 1', summary.stdout)
            self.assertIn('Anomalies: 1', summary.stdout)
            self.assertNotIn('Traceback', summary.stderr)


if __name__ == "__main__":
    unittest.main()
