"""Extended offline CLI for rolling latency incidents.

Use analyzer.py for the original backwards-compatible z-score demo.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Iterator, Mapping

from incident_engine import (
    AnalysisConfig,
    analyze_incidents,
    render_markdown,
    render_sarif,
    render_summary,
)

MAX_INPUT_BYTES = 20 * 1024 * 1024


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(
        description="Offline rolling latency analysis; never sends telemetry"
    )
    command.add_argument("input", type=Path, help="CSV or JSONL file")
    command.add_argument("--input-format", choices=("csv", "jsonl"), default="csv")
    command.add_argument("--method", choices=("mad", "zscore", "iqr"), default="mad")
    command.add_argument("--threshold", type=float, default=3.5)
    command.add_argument("--min-samples", type=int, default=5)
    command.add_argument("--window-size", type=int, default=40)
    command.add_argument("--cooldown-seconds", type=int, default=0)
    command.add_argument("--max-rows", type=int, default=100_000)
    command.add_argument("--service", action="append", default=[],
                         help="include only this service; repeatable")
    command.add_argument("--strict", action="store_true",
                         help="fail on invalid rows instead of reporting them")
    command.add_argument("--format", choices=("json", "summary", "markdown", "sarif"),
                         default="json")
    command.add_argument("--output", type=Path,
                         help="write output atomically instead of stdout")
    command.add_argument("--fail-on", choices=("none", "warning", "critical"),
                         default="none")
    return command


def read_csv(path: Path) -> Iterator[Mapping]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None:
            raise ValueError("CSV is empty or has no header")
        if "service" not in reader.fieldnames or "latency_ms" not in reader.fieldnames:
            raise ValueError("CSV requires service and latency_ms columns")
        if len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError("CSV contains duplicate column names")
        yield from reader


def read_jsonl(path: Path) -> Iterator[Mapping]:
    with path.open("r", encoding="utf-8-sig") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                yield None
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                yield None
                continue
            yield value


def read_input(path: Path, input_format: str) -> Iterator[Mapping]:
    if input_format == "csv":
        yield from read_csv(path)
    elif input_format == "jsonl":
        yield from read_jsonl(path)
    else:
        raise ValueError("unsupported input format")


def render(report, output_format: str, input_path: Path, input_format: str = "csv") -> str:
    if output_format == "json":
        return json.dumps(report.as_dict(), indent=2, ensure_ascii=False) + "\n"
    if output_format == "summary":
        return render_summary(report)
    if output_format == "markdown":
        return render_markdown(report)
    if output_format == "sarif":
        return json.dumps(render_sarif(report, input_path.name,
                                            line_offset=1 if input_format == "csv" else 0),
                          indent=2, ensure_ascii=False) + "\n"
    raise ValueError("unsupported output format")


def safe_write(destination: Path, content: str, input_path: Path) -> None:
    if destination.resolve() == input_path.resolve():
        raise ValueError("output must not overwrite the input file")
    if not destination.parent.is_dir():
        raise ValueError("output parent directory does not exist")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=destination.parent,
            prefix=".incident-",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(destination)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def run(argv: list[str] | None = None) -> int:
    command = parser()
    args = command.parse_args(argv)
    try:
        config = AnalysisConfig(
            method=args.method,
            threshold=args.threshold,
            min_samples=args.min_samples,
            window_size=args.window_size,
            cooldown_seconds=args.cooldown_seconds,
            services=tuple(args.service),
            strict=args.strict,
            max_rows=args.max_rows,
        )
        config.validate()
        if not args.input.is_file():
            raise ValueError("input must be an existing regular file")
        if args.input.stat().st_size > MAX_INPUT_BYTES:
            raise ValueError("input exceeds the 20 MiB safety limit")
        report = analyze_incidents(read_input(args.input, args.input_format), config)
        content = render(report, args.format, args.input, args.input_format)
        if args.output:
            safe_write(args.output, content, args.input)
        else:
            sys.stdout.write(content)
        return 3 if report.has_incidents(args.fail_on) else 0
    except (OSError, UnicodeError, csv.Error, ValueError, OverflowError) as error:
        command.exit(2, f"incident analysis error: {error}\n")


if __name__ == "__main__":
    raise SystemExit(run())
