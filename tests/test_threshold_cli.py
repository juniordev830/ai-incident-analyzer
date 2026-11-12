import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'analyzer.py'


class ThresholdCliTests(unittest.TestCase):
    def test_custom_threshold_detects_known_outlier(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory) / 'sample.csv'
            data.write_text('service,latency_ms\n' + ''.join(f'api,{v}\n' for v in [100, 99, 101, 100, 101, 99, 1000]), encoding='utf-8')
            result = subprocess.run([sys.executable, str(SCRIPT), str(data), '--threshold', '2.3'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(json.loads(result.stdout)['anomalies'][0]['latency_ms'], 1000)

    def test_invalid_threshold_fails_without_traceback(self):
        for threshold in ('0', '-1', 'nan', 'inf'):
            with self.subTest(threshold=threshold):
                result = subprocess.run([sys.executable, str(SCRIPT), 'unused.csv', '--threshold', threshold], capture_output=True, text=True)
                self.assertEqual(result.returncode, 2)
                self.assertIn('positive finite', result.stderr)
                self.assertNotIn('Traceback', result.stderr)

    def test_missing_required_columns_fail_with_clear_message(self):
        for header in ('service', 'latency_ms', 'service,', ''):
            with self.subTest(header=header):
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / 'invalid.csv'
                    path.write_text(header + '\\napi,20\\n', encoding='utf-8')
                    result = subprocess.run(
                        [sys.executable, str(SCRIPT), str(path)], capture_output=True, text=True
                    )
                    self.assertEqual(result.returncode, 2)
                    self.assertIn('CSV', result.stderr)
                    self.assertNotIn('Traceback', result.stderr)


if __name__ == '__main__':
    unittest.main()
