"""Statistical log latency anomaly detector, no ML claims or external telemetry."""
from __future__ import annotations
import argparse
import csv
import json
import math
import statistics
from pathlib import Path

def analyze(rows: list[dict], threshold: float = 2.5, min_samples: int = 6) -> list[dict]:
    if not math.isfinite(threshold) or threshold <= 0: raise ValueError('invalid threshold')
    if isinstance(min_samples, bool) or not isinstance(min_samples, int) or not 2 <= min_samples <= 10000:
        raise ValueError('invalid minimum sample count')
    valid = []
    for row in rows:
        try: value = float(row['latency_ms'])
        except (KeyError, TypeError, ValueError): continue
        if math.isfinite(value) and value >= 0: valid.append((str(row.get('service', 'unknown')), value))
    by_service = {}
    for service, duration in valid: by_service.setdefault(service, []).append(duration)
    baselines = {}
    for service, samples in by_service.items():
        if len(samples) >= min_samples:
            mean = statistics.mean(samples)
            stddev = statistics.pstdev(samples)
            baselines[service] = (mean, stddev)
    output = []
    for service, duration in valid:
        if service not in baselines: continue
        mean, stddev = baselines[service]
        if stddev > 0 and duration > mean and (duration - mean) / stddev >= threshold:
            output.append({'service': service, 'latency_ms': duration, 'z_score': round((duration-mean)/stddev,3)})
    return output

def read_latency_csv(stream) -> list[dict]:
    """Read a CSV, rejecting missing fields instead of returning a misleading empty report."""
    reader = csv.DictReader(stream)
    columns = reader.fieldnames
    if not columns:
        raise ValueError('CSV is empty or missing a header')
    if any(column is None or not column.strip() for column in columns):
        raise ValueError('CSV header contains an empty column name')
    required = {'service', 'latency_ms'}
    missing = sorted(required.difference(columns))
    if missing:
        raise ValueError(f"missing required CSV columns: {', '.join(missing)}")
    return list(reader)


def main():
    cli=argparse.ArgumentParser(description='Detect statistical high-latency anomalies')
    cli.add_argument('csv_file', help='CSV containing service,latency_ms')
    cli.add_argument('--threshold', type=float, default=2.5,
                     help='positive z-score threshold (default: 2.5)')
    cli.add_argument('--min-samples', type=int, default=6,
                     help='minimum samples per service to build a baseline (default: 6)')
    args=cli.parse_args()
    if not math.isfinite(args.threshold) or args.threshold <= 0:
        cli.error('threshold must be a positive finite number')
    if not 2 <= args.min_samples <= 10000:
        cli.error('min-samples must be between 2 and 10000')
    try:
        with Path(args.csv_file).open(newline='',encoding='utf-8') as file:
            results=analyze(read_latency_csv(file), threshold=args.threshold, min_samples=args.min_samples)
    except (OSError, UnicodeError, csv.Error, ValueError) as error:
        cli.error(f'cannot read CSV: {error}')
    print(json.dumps({'anomalies':results},indent=2))

if __name__=='__main__': main()
