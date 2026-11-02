"""Statistical log latency anomaly detector, no ML claims or external telemetry."""
from __future__ import annotations
import argparse
import csv
import json
import math
import statistics
from pathlib import Path

def analyze(rows: list[dict], threshold: float = 2.5) -> list[dict]:
    if not math.isfinite(threshold) or threshold <= 0: raise ValueError('invalid threshold')
    valid = []
    for row in rows:
        try: value = float(row['latency_ms'])
        except (KeyError, TypeError, ValueError): continue
        if math.isfinite(value) and value >= 0: valid.append((str(row.get('service', 'unknown')), value))
    by_service = {}
    for service, duration in valid: by_service.setdefault(service, []).append(duration)
    baselines = {}
    for service, samples in by_service.items():
        if len(samples) >= 6:
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

def main():
    cli=argparse.ArgumentParser(description='Detect statistical high-latency anomalies')
    cli.add_argument('csv_file', help='CSV containing service,latency_ms')
    cli.add_argument('--threshold', type=float, default=2.5,
                     help='positive z-score threshold (default: 2.5)')
    args=cli.parse_args()
    if not math.isfinite(args.threshold) or args.threshold <= 0:
        cli.error('threshold must be a positive finite number')
    try:
        with Path(args.csv_file).open(newline='',encoding='utf-8') as file:
            results=analyze(list(csv.DictReader(file)), threshold=args.threshold)
    except (OSError, UnicodeError, csv.Error) as error:
        cli.error(f'cannot read CSV: {error}')
    print(json.dumps({'anomalies':results},indent=2))

if __name__=='__main__': main()
