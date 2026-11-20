"""Offline, dependency-free latency incident analysis with causal baselines.

This module never connects to a service, sends telemetry or mutates input data.
"""
from __future__ import annotations

from collections import Counter, defaultdict, deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from math import ceil, floor, isfinite
from statistics import mean, median, pstdev
from typing import Iterable, Mapping


@dataclass(frozen=True)
class AnalysisConfig:
    method: str = "mad"
    threshold: float = 3.5
    min_samples: int = 5
    window_size: int = 40
    cooldown_seconds: int = 0
    services: tuple[str, ...] = ()
    strict: bool = False
    max_rows: int = 100_000

    def validate(self) -> None:
        if self.method not in ("mad", "zscore", "iqr"):
            raise ValueError("method must be mad, zscore or iqr")
        if isinstance(self.threshold, bool) or not isinstance(self.threshold, (int, float)):
            raise ValueError("threshold must be numeric")
        if not isfinite(self.threshold) or self.threshold <= 0:
            raise ValueError("threshold must be positive and finite")
        for name, value in (("min_samples", self.min_samples),
                            ("window_size", self.window_size),
                            ("cooldown_seconds", self.cooldown_seconds),
                            ("max_rows", self.max_rows)):
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{name} must be an integer")
        if not 2 <= self.min_samples <= 10_000:
            raise ValueError("min_samples must be between 2 and 10000")
        if not self.min_samples <= self.window_size <= 100_000:
            raise ValueError("window_size must be >= min_samples and <= 100000")
        if not 0 <= self.cooldown_seconds <= 31_536_000:
            raise ValueError("cooldown_seconds out of range")
        if not 1 <= self.max_rows <= 1_000_000:
            raise ValueError("max_rows out of range")
        if not isinstance(self.services, tuple):
            raise ValueError("services must be a tuple")
        if any(not isinstance(service, str) or not service.strip()
               for service in self.services):
            raise ValueError("service filters must be nonempty strings")
        if not isinstance(self.strict, bool):
            raise ValueError("strict must be boolean")


@dataclass(frozen=True)
class Event:
    row: int
    service: str
    latency_ms: float
    timestamp: datetime | None
    request_id: str | None


@dataclass(frozen=True)
class Rejection:
    row: int
    reason: str


@dataclass(frozen=True)
class Incident:
    id: str
    row: int
    service: str
    latency_ms: float
    baseline_ms: float
    score: float
    severity: str
    method: str
    sample_count: int
    timestamp: str | None


@dataclass
class AnalysisReport:
    config: AnalysisConfig
    accepted: int = 0
    rejected: list[Rejection] = field(default_factory=list)
    incidents: list[Incident] = field(default_factory=list)
    suppressed: int = 0
    services: dict[str, dict] = field(default_factory=dict)
    input_rows: int = 0

    def as_dict(self) -> dict:
        return {
            "schema_version": 1,
            "configuration": asdict(self.config),
            "input_rows": self.input_rows,
            "accepted_rows": self.accepted,
            "rejected_rows": len(self.rejected),
            "rejection_reasons": dict(sorted(Counter(
                item.reason for item in self.rejected).items())),
            "severity_counts": self.severity_counts(),
            "rejections": [asdict(item) for item in self.rejected],
            "suppressed_incidents": self.suppressed,
            "incidents": [asdict(item) for item in self.incidents],
            "services": self.services,
        }

    def severity_counts(self) -> dict[str, int]:
        counts = Counter(incident.severity for incident in self.incidents)
        return {"critical": counts["critical"], "warning": counts["warning"]}

    def has_incidents(self, minimum: str = "warning") -> bool:
        if minimum == "none":
            return False
        if minimum not in ("warning", "critical"):
            raise ValueError("minimum severity must be warning, critical or none")
        return any(item.severity == "critical" or
                   (minimum == "warning" and item.severity == "warning")
                   for item in self.incidents)


def parse_timestamp(raw: object) -> datetime | None:
    if raw is None or raw == "":
        return None
    if not isinstance(raw, str):
        raise ValueError("invalid_timestamp")
    try:
        value = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid_timestamp") from exc
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp_requires_timezone")
    return value.astimezone(timezone.utc)


def parse_event(row: Mapping, number: int) -> Event:
    if not isinstance(row, Mapping):
        raise ValueError("invalid_row")
    service = row.get("service")
    if not isinstance(service, str) or not service.strip():
        raise ValueError("missing_service")
    if any(ord(character) < 32 or ord(character) == 127 for character in service):
        raise ValueError("invalid_service")
    service = service.strip()
    if len(service) > 100:
        raise ValueError("service_too_long")
    raw_latency = row.get("latency_ms")
    if isinstance(raw_latency, bool) or raw_latency is None:
        raise ValueError("invalid_latency")
    try:
        latency = float(raw_latency)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("invalid_latency") from exc
    if not isfinite(latency) or latency < 0:
        raise ValueError("invalid_latency")
    timestamp = parse_timestamp(row.get("timestamp"))
    request_id = row.get("request_id")
    if request_id is not None:
        if not isinstance(request_id, str) or len(request_id) > 128:
            raise ValueError("invalid_request_id")
        if any(ord(character) < 32 or ord(character) == 127 for character in request_id):
            raise ValueError("invalid_request_id")
        request_id = request_id.strip() or None
    return Event(number, service, latency, timestamp, request_id)


def quantile(values: Iterable[float], fraction: float) -> float:
    """Linear interpolation, including endpoints, independent of input order."""
    if not isfinite(fraction) or not 0 <= fraction <= 1:
        raise ValueError("fraction must be between zero and one")
    ordered = sorted(values)
    if not ordered:
        raise ValueError("cannot compute quantile of empty values")
    position = (len(ordered) - 1) * fraction
    lower, upper = floor(position), ceil(position)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def baseline(values: Iterable[float], method: str) -> tuple[float, float]:
    """Return center and robust or classical scale for prior observations."""
    sample = list(values)
    if len(sample) < 2:
        raise ValueError("baseline needs at least two samples")
    if method == "zscore":
        center = mean(sample)
        scale = pstdev(sample)
    elif method == "mad":
        center = median(sample)
        scale = 1.4826 * median(abs(value - center) for value in sample)
    elif method == "iqr":
        center = median(sample)
        scale = (quantile(sample, 0.75) - quantile(sample, 0.25)) / 1.349
    else:
        raise ValueError("unknown baseline method")
    # Flat historical series must still detect a genuinely slower request.
    if scale <= 1e-12:
        scale = max(1.0, abs(center) * 0.01)
    return float(center), float(scale)


def score_latency(value: float, center: float, scale: float) -> float:
    if not all(isfinite(v) for v in (value, center, scale)) or scale <= 0:
        raise ValueError("invalid score inputs")
    return (value - center) / scale


def incident_identifier(event: Event, method: str) -> str:
    token = "|".join((event.service, str(event.row), event.request_id or "",
                      event.timestamp.isoformat() if event.timestamp else "", method))
    return sha256(token.encode("utf-8")).hexdigest()[:20]


def service_summary(events: list[Event], incidents: list[Incident]) -> dict:
    """Summarize accepted requests, not only requests with enough baseline."""
    if not events:
        raise ValueError("service summary requires events")
    latencies = [event.latency_ms for event in events]
    mid = len(latencies) // 2
    first = latencies[:mid]
    second = latencies[mid:]
    trend = None
    if first and second:
        trend = round(mean(second) - mean(first), 3)
    return {
        "samples": len(latencies),
        "mean_ms": round(mean(latencies), 3),
        "median_ms": round(median(latencies), 3),
        "p50_ms": round(quantile(latencies, 0.50), 3),
        "p95_ms": round(quantile(latencies, 0.95), 3),
        "p99_ms": round(quantile(latencies, 0.99), 3),
        "minimum_ms": min(latencies),
        "maximum_ms": max(latencies),
        "incidents": len(incidents),
        "critical": sum(item.severity == "critical" for item in incidents),
        "trend_second_half_minus_first_ms": trend,
    }


def analyze_incidents(rows: Iterable[Mapping], config: AnalysisConfig | None = None) -> AnalysisReport:
    """Causal rolling detection: a request never contributes to its own baseline.

    Timestamped service streams are sorted chronologically. Without complete
    timestamps, original input order is used for that service.
    """
    config = config or AnalysisConfig()
    config.validate()
    report = AnalysisReport(config=config)
    grouped: dict[str, list[Event]] = defaultdict(list)
    allowed = set(config.services)
    for number, row in enumerate(rows, 1):
        if number > config.max_rows:
            raise ValueError("maximum input row count exceeded")
        report.input_rows += 1
        try:
            event = parse_event(row, number)
        except ValueError as exc:
            report.rejected.append(Rejection(number, str(exc)))
            if config.strict:
                raise ValueError(f"row {number}: {exc}") from exc
            continue
        if allowed and event.service not in allowed:
            continue
        report.accepted += 1
        grouped[event.service].append(event)

    for service in sorted(grouped):
        events = grouped[service]
        if all(event.timestamp is not None for event in events):
            events = sorted(events, key=lambda event: (event.timestamp, event.row))
        history: deque[float] = deque(maxlen=config.window_size)
        last_emitted: datetime | None = None
        incidents: list[Incident] = []
        for event in events:
            if len(history) >= config.min_samples:
                center, scale = baseline(history, config.method)
                score = score_latency(event.latency_ms, center, scale)
                if event.latency_ms > center and score >= config.threshold:
                    timestamp = event.timestamp
                    cooling_down = (
                        config.cooldown_seconds > 0 and timestamp is not None
                        and last_emitted is not None
                        and 0 <= (timestamp - last_emitted).total_seconds()
                        < config.cooldown_seconds
                    )
                    if cooling_down:
                        report.suppressed += 1
                    else:
                        severity = "critical" if score >= 2 * config.threshold else "warning"
                        incident = Incident(
                            id=incident_identifier(event, config.method),
                            row=event.row,
                            service=service,
                            latency_ms=event.latency_ms,
                            baseline_ms=round(center, 3),
                            score=round(score, 3),
                            severity=severity,
                            method=config.method,
                            sample_count=len(history),
                            timestamp=timestamp.isoformat() if timestamp else None,
                        )
                        incidents.append(incident)
                        report.incidents.append(incident)
                        last_emitted = timestamp
            history.append(event.latency_ms)
        report.services[service] = service_summary(events, incidents)

    report.incidents.sort(key=lambda incident: (incident.service, incident.row))
    return report


def render_summary(report: AnalysisReport) -> str:
    counts = report.severity_counts()
    lines = [
        "Latency incident analysis",
        f"Input: {report.input_rows} | Accepted: {report.accepted} | Rejected: {len(report.rejected)}",
        f"Incidents: {len(report.incidents)} | Critical: {counts['critical']} | Warning: {counts['warning']}",
        f"Suppressed by cooldown: {report.suppressed}",
    ]
    for service, stats in sorted(report.services.items()):
        lines.append(
            f"{service}: {stats['samples']} samples, p95={stats['p95_ms']:.3f}ms, "
            f"incidents={stats['incidents']}"
        )
    for incident in report.incidents:
        lines.append(
            f"[{incident.severity.upper()}] {incident.service} row={incident.row} "
            f"latency={incident.latency_ms:.3f}ms score={incident.score:.3f}"
        )
    return "\n".join(lines) + "\n"


def render_markdown(report: AnalysisReport) -> str:
    lines = [
        "# Latency incident analysis",
        "",
        f"Accepted rows: **{report.accepted}**; rejected rows: **{len(report.rejected)}**.",
        f"Detected incidents: **{len(report.incidents)}**; suppressed: **{report.suppressed}**.",
        "",
        "| Service | Samples | P95 (ms) | Incidents |",
        "| --- | ---: | ---: | ---: |",
    ]
    for name, stats in sorted(report.services.items()):
        safe_name = name.replace("|", r"\|").replace("\n", " ")
        lines.append(
            f"| {safe_name} | {stats['samples']} | {stats['p95_ms']:.3f} | {stats['incidents']} |"
        )
    lines += [
        "",
        "| Severity | Service | Row | Latency (ms) | Score |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    for incident in report.incidents:
        safe_name = incident.service.replace("|", r"\|").replace("\n", " ")
        lines.append(
            f"| {incident.severity} | {safe_name} | {incident.row} | "
            f"{incident.latency_ms:.3f} | {incident.score:.3f} |"
        )
    return "\n".join(lines) + "\n"


def render_sarif(report: AnalysisReport, artifact: str, line_offset: int = 1) -> dict:
    """SARIF 2.1.0 annotations point to original CSV or JSONL rows."""
    if line_offset not in (0, 1):
        raise ValueError("line_offset must be 0 or 1")
    results = []
    for incident in report.incidents:
        results.append({
            "ruleId": "LATENCY-OUTLIER",
            "level": "error" if incident.severity == "critical" else "warning",
            "message": {"text": (
                f"{incident.service}: {incident.latency_ms:.3f} ms "
                f"({incident.score:.3f} above rolling baseline)"
            )},
            "locations": [{"physicalLocation": {
                "artifactLocation": {"uri": artifact},
                "region": {"startLine": incident.row + line_offset},
            }}],
            "partialFingerprints": {"incidentId": incident.id},
        })
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {"driver": {
                "name": "ai-incident-analyzer",
                "informationUri": "https://github.com/juniordev830/ai-incident-analyzer",
                "rules": [{
                    "id": "LATENCY-OUTLIER",
                    "shortDescription": {"text": "High latency relative to historical requests"},
                    "defaultConfiguration": {"level": "warning"},
                }],
            }},
            "results": results,
        }],
    }
