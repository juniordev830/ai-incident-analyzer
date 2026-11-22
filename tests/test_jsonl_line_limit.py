from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from incident_cli import read_jsonl


class JsonlLineLimitTests(unittest.TestCase):
    def test_giant_record_is_rejected_without_losing_later_rows(self):
        with TemporaryDirectory() as folder:
            source = Path(folder) / "latencies.jsonl"
            source.write_text('"' + 'x' * 1_000_001 + '"\n' +
                              '{"service":"worker","latency_ms":42}\n', encoding="utf-8")
            rows = list(read_jsonl(source))
        self.assertEqual(rows[0], None)
        self.assertEqual(rows[1], {"service": "worker", "latency_ms": 42})


if __name__ == "__main__":
    unittest.main()
