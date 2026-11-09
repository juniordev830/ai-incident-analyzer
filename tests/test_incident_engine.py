"""Regression and edge-case tests for causal latency incident analysis."""
import math
import unittest
from datetime import datetime, timezone

from incident_engine import (
    AnalysisConfig,
    Event,
    analyze_incidents,
    baseline,
    incident_identifier,
    parse_event,
    parse_timestamp,
    quantile,
    render_markdown,
    render_sarif,
    render_summary,
    score_latency,
    service_summary,
)


def rows(values, service="api", **extra):
    return [{"service": service, "latency_ms": value, **extra} for value in values]


def detected(values, **config):
    return analyze_incidents(rows(values), AnalysisConfig(**config))


class ConfigurationTests(unittest.TestCase):
    def test_default_configuration_is_valid(self):
        AnalysisConfig().validate()

    def test_each_supported_method(self):
        for method in ("mad", "zscore", "iqr"):
            with self.subTest(method=method):
                AnalysisConfig(method=method).validate()

    def test_unknown_method_rejected(self):
        with self.assertRaisesRegex(ValueError, "method"):
            AnalysisConfig(method="neural").validate()

    def test_threshold_rejects_invalid_values(self):
        for value in (0, -1, float("nan"), float("inf"), True, "4"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    AnalysisConfig(threshold=value).validate()

    def test_minimum_sample_bounds(self):
        for value in (1, 0, 10001, True, 2.0):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    AnalysisConfig(min_samples=value).validate()

    def test_window_must_fit_minimum_samples(self):
        with self.assertRaisesRegex(ValueError, "window_size"):
            AnalysisConfig(min_samples=10, window_size=9).validate()

    def test_window_maximum_is_enforced(self):
        with self.assertRaises(ValueError):
            AnalysisConfig(window_size=100001).validate()

    def test_cooldown_must_be_nonnegative_integer(self):
        for value in (-1, 1.5, True, 31536001):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    AnalysisConfig(cooldown_seconds=value).validate()

    def test_max_rows_is_bounded(self):
        for value in (0, -1, True, 1000001):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    AnalysisConfig(max_rows=value).validate()

    def test_service_filter_requires_tuple(self):
        with self.assertRaises(ValueError):
            AnalysisConfig(services=["api"]).validate()

    def test_service_filter_requires_nonempty_names(self):
        for value in (("",), (None,), ("api", "")):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    AnalysisConfig(services=value).validate()

    def test_strict_requires_boolean(self):
        with self.assertRaises(ValueError):
            AnalysisConfig(strict=1).validate()


class ParsingTests(unittest.TestCase):
    def test_valid_event(self):
        event = parse_event({"service": " api ", "latency_ms": "12.5"}, 4)
        self.assertEqual(event.row, 4)
        self.assertEqual(event.service, "api")
        self.assertEqual(event.latency_ms, 12.5)
        self.assertIsNone(event.timestamp)

    def test_valid_zero_latency(self):
        self.assertEqual(parse_event({"service": "api", "latency_ms": 0}, 1).latency_ms, 0)

    def test_missing_service(self):
        for service in (None, "", "  ", 1):
            with self.subTest(service=service):
                with self.assertRaisesRegex(ValueError, "missing_service"):
                    parse_event({"service": service, "latency_ms": 10}, 1)

    def test_service_length_limit(self):
        with self.assertRaisesRegex(ValueError, "service_too_long"):
            parse_event({"service": "x" * 101, "latency_ms": 1}, 1)

    def test_invalid_latency(self):
        for value in (None, "", "oops", -1, True, float("nan"), float("inf")):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "invalid_latency"):
                    parse_event({"service": "api", "latency_ms": value}, 1)

    def test_invalid_non_mapping_row(self):
        with self.assertRaisesRegex(ValueError, "invalid_row"):
            parse_event(None, 1)

    def test_iso_timestamp_is_normalized_to_utc(self):
        result = parse_timestamp("2026-11-08T09:00:00+03:00")
        self.assertEqual(result.isoformat(), "2026-11-08T06:00:00+00:00")

    def test_zulu_timestamp(self):
        self.assertEqual(parse_timestamp("2026-11-08T06:00:00Z").tzinfo, timezone.utc)

    def test_absent_timestamp_is_allowed(self):
        self.assertIsNone(parse_timestamp(None))
        self.assertIsNone(parse_timestamp(""))

    def test_timezone_is_required(self):
        with self.assertRaisesRegex(ValueError, "timezone"):
            parse_timestamp("2026-11-08T06:00:00")

    def test_invalid_timestamp(self):
        for value in ("yesterday", 123, "2026-99-99T00:00:00Z"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "invalid_timestamp"):
                    parse_timestamp(value)

    def test_request_identifier_is_optional(self):
        event = parse_event({"service": "api", "latency_ms": 2, "request_id": "  r-1  "}, 1)
        self.assertEqual(event.request_id, "r-1")

    def test_request_identifier_has_length_limit(self):
        with self.assertRaisesRegex(ValueError, "invalid_request_id"):
            parse_event({"service": "api", "latency_ms": 2, "request_id": "x" * 129}, 1)

    def test_request_identifier_must_be_text(self):
        with self.assertRaisesRegex(ValueError, "invalid_request_id"):
            parse_event({"service": "api", "latency_ms": 2, "request_id": 2}, 1)


class StatisticsTests(unittest.TestCase):
    def test_quantiles_interpolate(self):
        self.assertEqual(quantile([0, 10, 20, 30], 0.25), 7.5)
        self.assertEqual(quantile([0, 10, 20, 30], 0.75), 22.5)

    def test_quantiles_do_not_depend_on_input_order(self):
        self.assertEqual(quantile([30, 10, 0, 20], 0.5), 15)

    def test_quantile_endpoints(self):
        self.assertEqual(quantile([8, 2, 4], 0), 2)
        self.assertEqual(quantile([8, 2, 4], 1), 8)

    def test_quantile_rejects_empty_values(self):
        with self.assertRaises(ValueError):
            quantile([], 0.5)

    def test_quantile_rejects_invalid_fractions(self):
        for value in (-0.1, 1.1, float("nan")):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    quantile([1, 2], value)

    def test_mad_is_resistant_to_outlier(self):
        center, scale = baseline([100, 100, 101, 99, 1000], "mad")
        self.assertEqual(center, 100)
        self.assertGreater(scale, 0)

    def test_zscore_uses_population_standard_deviation(self):
        center, scale = baseline([1, 2, 3], "zscore")
        self.assertEqual(center, 2)
        self.assertAlmostEqual(scale, math.sqrt(2 / 3))

    def test_iqr_center_and_scale(self):
        center, scale = baseline([1, 2, 3, 4, 5], "iqr")
        self.assertEqual(center, 3)
        self.assertAlmostEqual(scale, 2 / 1.349)

    def test_constant_baseline_has_safe_scale(self):
        for method in ("mad", "zscore", "iqr"):
            with self.subTest(method=method):
                center, scale = baseline([100] * 6, method)
                self.assertEqual(center, 100)
                self.assertGreater(scale, 0)

    def test_baseline_rejects_too_few_samples(self):
        with self.assertRaises(ValueError):
            baseline([1], "mad")

    def test_baseline_rejects_unknown_method(self):
        with self.assertRaises(ValueError):
            baseline([1, 2], "unknown")

    def test_score_latency_rejects_invalid_scale(self):
        with self.assertRaises(ValueError):
            score_latency(2, 1, 0)

    def test_score_latency_rejects_nonfinite_values(self):
        with self.assertRaises(ValueError):
            score_latency(float("nan"), 1, 2)

    def test_score_latency_returns_signed_difference(self):
        self.assertEqual(score_latency(10, 20, 2), -5)


class DetectionTests(unittest.TestCase):
    def test_detects_outlier_after_warmup(self):
        report = detected([100] * 6 + [1000])
        self.assertEqual(len(report.incidents), 1)
        self.assertEqual(report.incidents[0].row, 7)
        self.assertEqual(report.incidents[0].severity, "critical")

    def test_does_not_use_future_values_as_baseline(self):
        report = detected([1000] + [100] * 6)
        self.assertEqual(report.incidents, [])

    def test_first_rows_are_only_warmup(self):
        report = detected([1000, 1000, 1000], min_samples=5)
        self.assertEqual(report.incidents, [])

    def test_normal_requests_are_not_incidents(self):
        self.assertEqual(detected([100] * 20).incidents, [])

    def test_fast_requests_are_not_incidents(self):
        self.assertEqual(detected([100] * 6 + [0]).incidents, [])

    def test_multiple_services_have_isolated_baselines(self):
        data = rows([100] * 6, "api") + rows([1000] * 6, "db")
        data += rows([1000], "api") + rows([1000], "db")
        report = analyze_incidents(data)
        self.assertEqual([(x.service, x.latency_ms) for x in report.incidents],
                         [("api", 1000.0)])

    def test_service_filter_limits_analysis(self):
        data = rows([100] * 6 + [1000], "api") + rows([100] * 6 + [1000], "db")
        report = analyze_incidents(data, AnalysisConfig(services=("db",)))
        self.assertEqual(report.accepted, 7)
        self.assertEqual(set(report.services), {"db"})

    def test_invalid_rows_are_counted_without_sensitive_content(self):
        report = analyze_incidents([{"service": "api", "latency_ms": "secret"}])
        self.assertEqual(report.accepted, 0)
        self.assertEqual(report.as_dict()["rejection_reasons"], {"invalid_latency": 1})
        self.assertNotIn("secret", str(report.as_dict()))

    def test_strict_mode_reports_row_number(self):
        with self.assertRaisesRegex(ValueError, "row 2"):
            analyze_incidents(rows([100]) + [None], AnalysisConfig(strict=True))

    def test_input_limit_is_enforced(self):
        with self.assertRaisesRegex(ValueError, "maximum input"):
            analyze_incidents(rows([100] * 4), AnalysisConfig(max_rows=3))

    def test_all_methods_detect_large_outlier(self):
        for method in ("mad", "zscore", "iqr"):
            with self.subTest(method=method):
                report = detected([100] * 6 + [1000], method=method)
                self.assertEqual(len(report.incidents), 1)

    def test_window_size_is_respected(self):
        report = detected([100] * 6 + [1000], window_size=5)
        self.assertEqual(report.incidents[0].sample_count, 5)

    def test_severity_thresholds(self):
        report = detected([100] * 6 + [105], threshold=3.5)
        self.assertEqual(report.incidents[0].severity, "warning")

    def test_critical_is_more_severe_than_warning(self):
        report = detected([100] * 6 + [105, 1000], threshold=3.5)
        self.assertEqual(report.incidents[0].severity, "warning")
        self.assertEqual(report.incidents[1].severity, "critical")

    def test_timestamped_rows_are_sorted_for_baseline(self):
        data = rows([1000], timestamp="2026-01-01T00:00:07Z")
        data += [dict(row, timestamp=f"2026-01-01T00:00:0{i}Z")
                 for i, row in enumerate(rows([100] * 6), 1)]
        report = analyze_incidents(data)
        self.assertEqual(report.incidents[0].row, 1)

    def test_missing_timestamps_preserve_input_order(self):
        data = rows([1000]) + rows([100] * 6, timestamp="2026-01-01T00:00:00Z")
        self.assertEqual(analyze_incidents(data).incidents, [])

    def test_cooldown_suppresses_repeated_incidents(self):
        data = [dict(row, timestamp=f"2026-01-01T00:00:{i:02d}Z")
                for i, row in enumerate(rows([100] * 6 + [1000, 1000]))]
        report = analyze_incidents(data, AnalysisConfig(cooldown_seconds=30))
        self.assertEqual(len(report.incidents), 1)
        self.assertEqual(report.suppressed, 1)

    def test_without_timestamps_cooldown_does_not_suppress(self):
        report = detected([100] * 6 + [1000, 1000], cooldown_seconds=30)
        self.assertEqual(len(report.incidents), 2)

    def test_incident_ids_are_deterministic(self):
        event = Event(1, "api", 1000, datetime.now(timezone.utc), "r1")
        self.assertEqual(incident_identifier(event, "mad"),
                         incident_identifier(event, "mad"))

    def test_incident_ids_change_with_method(self):
        event = Event(1, "api", 1000, None, "r1")
        self.assertNotEqual(incident_identifier(event, "mad"),
                            incident_identifier(event, "zscore"))

    def test_reports_serialize_without_nonfinite_values(self):
        report = detected([100] * 6 + [1000])
        self.assertNotIn("Infinity", str(report.as_dict()))
        self.assertEqual(report.as_dict()["schema_version"], 1)

    def test_severity_counts_and_fail_on(self):
        report = detected([100] * 6 + [1000])
        self.assertEqual(report.severity_counts(), {"critical": 1, "warning": 0})
        self.assertTrue(report.has_incidents("critical"))
        self.assertTrue(report.has_incidents("warning"))
        self.assertFalse(report.has_incidents("none"))

    def test_fail_on_invalid_severity(self):
        with self.assertRaises(ValueError):
            detected([100]).has_incidents("emergency")


class ReportingTests(unittest.TestCase):
    def test_summary_includes_service_and_counts(self):
        text = render_summary(detected([100] * 6 + [1000]))
        self.assertIn("api:", text)
        self.assertIn("Critical: 1", text)

    def test_markdown_includes_tables(self):
        text = render_markdown(detected([100] * 6 + [1000]))
        self.assertIn("| Service | Samples |", text)
        self.assertIn("| critical |", text)

    def test_markdown_escapes_service_pipe(self):
        text = render_markdown(analyze_incidents(rows([100], "api|east")))
        self.assertIn(r"api\|east", text)

    def test_sarif_has_correct_row_after_csv_header(self):
        report = detected([100] * 6 + [1000])
        sarif = render_sarif(report, "latencies.csv")
        self.assertEqual(sarif["version"], "2.1.0")
        self.assertEqual(sarif["runs"][0]["results"][0]["locations"][0]
                         ["physicalLocation"]["region"]["startLine"], 8)

    def test_sarif_empty_results_are_valid(self):
        sarif = render_sarif(detected([100] * 7), "latencies.csv")
        self.assertEqual(sarif["runs"][0]["results"], [])

    def test_service_summary_tracks_percentiles(self):
        events = [Event(i, "api", float(i), None, None) for i in range(1, 11)]
        summary = service_summary(events, [])
        self.assertEqual(summary["samples"], 10)
        self.assertEqual(summary["minimum_ms"], 1)
        self.assertEqual(summary["maximum_ms"], 10)
        self.assertGreater(summary["p95_ms"], 9)

    def test_service_summary_requires_events(self):
        with self.assertRaises(ValueError):
            service_summary([], [])

    def test_rejection_reasons_are_grouped(self):
        report = analyze_incidents([None, None, {"service": "api", "latency_ms": -1}])
        self.assertEqual(report.as_dict()["rejection_reasons"],
                         {"invalid_latency": 1, "invalid_row": 2})


    def test_sarif_jsonl_uses_one_based_row_without_header(self):
        report = detected([100] * 6 + [1000])
        sarif = render_sarif(report, "events.jsonl", line_offset=0)
        self.assertEqual(sarif["runs"][0]["results"][0]["locations"][0]
                         ["physicalLocation"]["region"]["startLine"], 7)

    def test_sarif_rejects_invalid_line_offset(self):
        with self.assertRaises(ValueError):
            render_sarif(detected([100] * 6 + [1000]), "events.csv", line_offset=2)


if __name__ == "__main__":
    unittest.main()

class ReportSafetyRegressionTests(unittest.TestCase):
    def test_rejects_control_characters_in_service_names(self):
        for name in ("api\nINFO forged", "api\rprogress", "api\tother", "api\x1b[31m", "api\x7f"):
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError, "invalid_service"):
                    parse_event({"service": name, "latency_ms": 100}, 1)

    def test_rejects_control_characters_in_request_ids(self):
        for identifier in ("req\nsecondary", "req\x1b[2J", "req\tother"):
            with self.subTest(identifier=identifier):
                with self.assertRaisesRegex(ValueError, "invalid_request_id"):
                    parse_event({"service": "api", "latency_ms": 100,
                                 "request_id": identifier}, 1)

    def test_rejected_labels_cannot_inject_terminal_lines(self):
        report = analyze_incidents([
            {"service": "api\n[CRITICAL] forged", "latency_ms": 30},
            {"service": "api", "latency_ms": 10},
        ])
        self.assertEqual(report.accepted, 1)
        self.assertEqual(report.as_dict()["rejection_reasons"], {"invalid_service": 1})
        self.assertNotIn("forged", render_summary(report))

    def test_json_exposes_aggregate_severity_counts(self):
        report = analyze_incidents([{"service": "api", "latency_ms": 10}])
        self.assertEqual(report.as_dict()["severity_counts"],
                         {"critical": 0, "warning": 0})
