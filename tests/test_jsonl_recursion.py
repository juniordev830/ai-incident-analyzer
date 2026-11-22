from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from incident_cli import read_jsonl


class DeepJsonlTests(unittest.TestCase):
    def test_deeply_nested_object_does_not_crash_parser(self):
        with TemporaryDirectory() as folder:
            file = Path(folder) / "logs.jsonl"
            file.write_text("[" * 20_000 + "0" + "]" * 20_000 + "\n" +
                            '{"service":"api","latency_ms":30}\n', encoding="utf-8")
            rows = list(read_jsonl(file))
        self.assertEqual(rows[0], None)
        self.assertEqual(rows[1]["service"], "api")

    def test_regular_jsonl_sample_remains_accepted(self):
        with TemporaryDirectory() as folder:
            file = Path(folder) / "logs.jsonl"
            file.write_text('{"service":"api","latency_ms":20}\n', encoding="utf-8")
            self.assertEqual(list(read_jsonl(file))[0]["latency_ms"], 20)


if __name__ == "__main__":
    unittest.main()
