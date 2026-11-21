import csv
import io
import unittest
from pathlib import Path
from analyzer import analyze, read_latency_csv

class AnalyzerTests(unittest.TestCase):
    def test_legacy_analyzer_skips_unsafe_service_and_boolean_latency(self):
        rows = [{'service': service, 'latency_ms': value}
                for service, value in [('api', True), ('', 10), ('api\nforged', 500),
                                       (['bad'], 50), ('api', 100)]]
        self.assertEqual(analyze(rows, min_samples=2), [])
        with self.assertRaisesRegex(ValueError, 'rows'):
            analyze(None)
        with self.assertRaisesRegex(ValueError, '100000'):
            analyze([{}] * 100_001)

    def test_csv_record_limit_and_boundary(self):
        data = 'service,latency_ms\n' + 'api,12\n' * 100_001
        with self.assertRaisesRegex(ValueError, '100000'):
            read_latency_csv(io.StringIO(data))
        self.assertEqual(len(read_latency_csv(io.StringIO(
            'service,latency_ms\n' + 'api,12\n' * 100_000))), 100_000)

    def test_detects_large_outlier(self):
        data=[{'service':'api','latency_ms':str(x)} for x in [100,99,101,100,101,99,1000]]
        out=analyze(data,threshold=2.3)
        self.assertEqual(len(out),1)
        self.assertEqual(out[0]['latency_ms'],1000)
    def test_documented_example_with_default_threshold(self):
        sample = Path(__file__).resolve().parents[1] / 'examples' / 'latencies.csv'
        with sample.open(newline='', encoding='utf-8') as stream:
            anomalies = analyze(list(csv.DictReader(stream)))
        self.assertEqual([(item['service'], item['latency_ms']) for item in anomalies],
                         [('api', 1000.0)])

    def test_custom_minimum_sample_count(self):
        data = [{'service': 'api', 'latency_ms': str(value)} for value in [100, 100, 100, 100, 1000]]
        self.assertEqual(len(analyze(data, threshold=2.0, min_samples=5)), 1)
        with self.assertRaises(ValueError):
            analyze(data, min_samples=1)

    def test_drops_invalid_and_small_samples(self):
        self.assertEqual(analyze([{'service':'api','latency_ms':'nan'},{'service':'api','latency_ms':'100'}]),[])
    def test_rejects_bad_threshold(self):
        with self.assertRaises(ValueError): analyze([],threshold=0)

    def test_csv_rejects_duplicate_columns_and_rows_with_missing_or_extra_fields(self):
        for text, error in [
            ('service,latency_ms,latency_ms\napi,10,11\n', 'duplicate'),
            ('service,latency_ms\napi\n', 'line 2'),
            ('service,latency_ms\napi,10,11\n', 'line 2'),
        ]:
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, error):
                read_latency_csv(io.StringIO(text))

    def test_csv_accepts_quoted_service_names(self):
        rows = read_latency_csv(io.StringIO('service,latency_ms\n"api, interna",10\n'))
        self.assertEqual(rows, [{'service': 'api, interna', 'latency_ms': '10'}])

if __name__=='__main__':unittest.main()
