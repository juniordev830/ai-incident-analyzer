"""Strict JSONL parsing prevents ambiguous or invalid incident records."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from incident_cli import read_jsonl


class JsonlSafetyTests(unittest.TestCase):
    def test_rejects_nonfinite_numbers_and_duplicate_fields(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "samples.jsonl"
            path.write_text(
                '{"service":"api","latency_ms":12}\n'
                '{"service":"api","latency_ms":NaN}\n'
                '{"service":"api","latency_ms":Infinity}\n'
                '{"service":"api","service":"other","latency_ms":10}\n',
                encoding="utf-8",
            )
            rows = list(read_jsonl(path))
        self.assertEqual(rows[0], {"service": "api", "latency_ms": 12})
        self.assertEqual(rows[1:], [None, None, None])


if __name__ == "__main__":
    unittest.main()
