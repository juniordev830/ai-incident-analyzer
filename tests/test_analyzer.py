import unittest
from analyzer import analyze

class AnalyzerTests(unittest.TestCase):
    def test_detects_large_outlier(self):
        data=[{'service':'api','latency_ms':str(x)} for x in [100,99,101,100,101,99,1000]]
        out=analyze(data,threshold=2.3)
        self.assertEqual(len(out),1)
        self.assertEqual(out[0]['latency_ms'],1000)
    def test_drops_invalid_and_small_samples(self):
        self.assertEqual(analyze([{'service':'api','latency_ms':'nan'},{'service':'api','latency_ms':'100'}]),[])
    def test_rejects_bad_threshold(self):
        with self.assertRaises(ValueError): analyze([],threshold=0)
if __name__=='__main__':unittest.main()
