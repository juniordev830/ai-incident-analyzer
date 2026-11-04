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


def analyze_report(rows: list[dict], threshold: float = 2.5,
                   min_samples: int = 6) -> dict:
    """Explain the per-service statistical baselines without changing detection.

    Invalid or negative latency measurements are excluded exactly as in analyze().
    Services with too few samples have no baseline and no anomaly decisions.
    """
    anomalies = analyze(rows, threshold=threshold, min_samples=min_samples)
    valid_by_service: dict[str, list[float]] = {}
    ignored = 0
    for row in rows:
        try:
            duration = float(row['latency_ms'])
        except (KeyError, TypeError, ValueError):
            ignored += 1
            continue
        if not math.isfinite(duration) or duration < 0:
            ignored += 1
            continue
        service = str(row.get('service', 'unknown'))
        valid_by_service.setdefault(service, []).append(duration)

    counts: dict[str, int] = {}
    for incident in anomalies:
        counts[incident['service']] = counts.get(incident['service'], 0) + 1

    baselines = []
    for service, samples in sorted(valid_by_service.items()):
        eligible = len(samples) >= min_samples
        baselines.append({
            'service': service,
            'samples': len(samples),
            'baseline_available': eligible,
            'mean_ms': round(statistics.mean(samples), 3) if eligible else None,
            'stddev_ms': round(statistics.pstdev(samples), 3) if eligible else None,
            'anomalies': counts.get(service, 0),
        })
    return {
        'total_rows': len(rows),
        'accepted_rows': len(rows) - ignored,
        'ignored_rows': ignored,
        'threshold': threshold,
        'min_samples': min_samples,
        'baselines': baselines,
        'anomalies': anomalies,
    }

def main():
    cli=argparse.ArgumentParser(description='Detect statistical high-latency anomalies')
    cli.add_argument('csv_file', help='CSV containing service,latency_ms')
    cli.add_argument('--threshold', type=float, default=2.5,
                     help='positive z-score threshold (default: 2.5)')
    cli.add_argument('--min-samples', type=int, default=6,
                     help='minimum samples per service to build a baseline (default: 6)')
    cli.add_argument('--format', choices=('json', 'report', 'summary'), default='json',
                     help='json: legacy anomalies; report: diagnostics JSON; summary: text')
    args=cli.parse_args()
    if not math.isfinite(args.threshold) or args.threshold <= 0:
        cli.error('threshold must be a positive finite number')
    if not 2 <= args.min_samples <= 10000:
        cli.error('min-samples must be between 2 and 10000')
    try:
        with Path(args.csv_file).open(newline='',encoding='utf-8') as file:
            rows = list(csv.DictReader(file))
            report = analyze_report(rows, threshold=args.threshold, min_samples=args.min_samples)
    except (OSError, UnicodeError, csv.Error) as error:
        cli.error(f'cannot read CSV: {error}')
    if args.format == 'json':
        print(json.dumps({'anomalies': report['anomalies']}, indent=2))
    elif args.format == 'report':
        print(json.dumps(report, indent=2))
    else:
        print(f"Rows: {report['total_rows']} | Valid: {report['accepted_rows']} | Ignored: {report['ignored_rows']}")
        for baseline in report['baselines']:
            if not baseline['baseline_available']:
                print(f"{baseline['service']}: {baseline['samples']} samples (insufficient baseline)")
            else:
                print(f"{baseline['service']}: {baseline['samples']} samples | mean={baseline['mean_ms']} ms "
                      f"| stddev={baseline['stddev_ms']} ms | anomalies={baseline['anomalies']}")
        print(f"Anomalies: {len(report['anomalies'])}")

if __name__=='__main__': main()
