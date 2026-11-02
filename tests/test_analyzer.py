import csv
import unittest
from pathlib import Path
from analyzer import analyze

class AnalyzerTests(unittest.TestCase):
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

    def test_drops_invalid_and_small_samples(self):
        self.assertEqual(analyze([{'service':'api','latency_ms':'nan'},{'service':'api','latency_ms':'100'}]),[])
    def test_rejects_bad_threshold(self):
        with self.assertRaises(ValueError): analyze([],threshold=0)
if __name__=='__main__':unittest.main()
