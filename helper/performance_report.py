import json
import os
import threading
import time
from datetime import datetime, timezone

try:
    from django.conf import settings
except Exception:  # pragma: no cover - settings may be unavailable at import time
    settings = None

from django.db import connection


class PerformanceReport:
    _instance = None
    _instance_lock = threading.Lock()

    def __init__(self):
        self._tests = []
        self._concurrency = []
        self._metrics = []
        self._errors = []
        self._printed = False
        self._lock = threading.Lock()

    @classmethod
    def instance(cls):
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
        return cls._instance

    def record_test(self, name, duration_s, queries, extra=None):
        item = {
            "name": name,
            "duration_s": float(duration_s),
            "queries": int(queries),
            "extra": extra or {},
        }
        with self._lock:
            self._tests.append(item)

    def record_concurrency(
        self,
        name,
        attempts,
        successes,
        errors,
        expected_exact=None,
        expected_max=None,
        note=None,
    ):
        error_types = {}
        for err in errors or []:
            err_name = type(err).__name__
            error_types[err_name] = error_types.get(err_name, 0) + 1

        item = {
            "name": name,
            "attempts": int(attempts),
            "successes": int(successes),
            "error_count": len(errors or []),
            "error_types": error_types,
            "expected_exact": expected_exact,
            "expected_max": expected_max,
            "note": note,
        }
        with self._lock:
            self._concurrency.append(item)

    def record_metric(self, name, metric, value, unit=None, extra=None):
        item = {
            "name": name,
            "metric": metric,
            "value": value,
            "unit": unit,
            "extra": extra or {},
        }
        with self._lock:
            self._metrics.append(item)

    def record_error(self, name, error):
        item = {
            "name": name,
            "error": str(error),
        }
        with self._lock:
            self._errors.append(item)

    def _get_thresholds(self):
        defaults = {
            "duration_s": {"warning": 0.5, "critical": 1.0},
            "queries": {"warning": 50, "critical": 120},
        }
        if settings is None:
            return defaults

        overrides = getattr(settings, "PERF_THRESHOLDS", None)
        if not isinstance(overrides, dict):
            return defaults

        for key in ("duration_s", "queries"):
            if key in overrides and isinstance(overrides[key], dict):
                for level in ("warning", "critical"):
                    if level in overrides[key]:
                        try:
                            defaults[key][level] = float(overrides[key][level])
                        except (TypeError, ValueError):
                            pass
        return defaults

    def _level_by_threshold(self, value, thresholds):
        if value >= thresholds["critical"]:
            return "critical"
        if value >= thresholds["warning"]:
            return "warning"
        return "good"

    def _classify_test(self, item, thresholds):
        duration_level = self._level_by_threshold(
            item["duration_s"], thresholds["duration_s"]
        )
        query_level = self._level_by_threshold(item["queries"], thresholds["queries"])
        order = {"good": 0, "warning": 1, "critical": 2}
        level = duration_level
        if order[query_level] > order[level]:
            level = query_level

        tags = []
        if duration_level != "good":
            tags.append(f"duration-{duration_level}")
        if query_level != "good":
            tags.append(f"queries-{query_level}")

        return {
            "level": level,
            "duration_level": duration_level,
            "query_level": query_level,
            "tags": tags,
        }

    def _classify_concurrency(self, record):
        reasons = []
        status = "ok"

        if record["error_count"] > 0:
            status = "error"
            reasons.append("errors")

        if record["expected_exact"] is not None and record["successes"] != record["expected_exact"]:
            status = "error"
            reasons.append("expected_exact")

        if record["expected_max"] is not None and record["successes"] > record["expected_max"]:
            status = "error"
            reasons.append("expected_max")

        if status == "ok" and record["successes"] < record["attempts"]:
            status = "contention"
            reasons.append("contention")

        return status, reasons

    def _concurrency_level(self, status):
        mapping = {"ok": "good", "contention": "warning", "error": "critical"}
        return mapping.get(status, "warning")

    def _build_payload(self, snapshot):
        thresholds = self._get_thresholds()
        tests = []
        for item in snapshot["tests"]:
            enriched = dict(item)
            enriched["classification"] = self._classify_test(item, thresholds)
            tests.append(enriched)

        concurrency = []
        for item in snapshot["concurrency"]:
            status, reasons = self._classify_concurrency(item)
            enriched = dict(item)
            enriched["status"] = status
            enriched["reasons"] = reasons
            enriched["level"] = self._concurrency_level(status)
            concurrency.append(enriched)

        return {
            "report_meta": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "thresholds": thresholds,
            },
            "tests": tests,
            "concurrency": concurrency,
            "metrics": list(snapshot["metrics"]),
            "errors": list(snapshot["errors"]),
        }

    def _summarize(self, payload):
        tests = payload["tests"]
        concurrency = payload["concurrency"]
        metrics = payload["metrics"]
        errors = payload["errors"]
        thresholds = payload["report_meta"]["thresholds"]

        lines = []
        lines.append("=== Performance Report ===")
        lines.append(
            f"tests={len(tests)} concurrency_cases={len(concurrency)} metrics={len(metrics)} errors={len(errors)}"
        )
        lines.append("")

        if tests:
            lines.append(
                "Thresholds: duration warning >= %.2fs, critical >= %.2fs | queries warning >= %d, critical >= %d"
                % (
                    thresholds["duration_s"]["warning"],
                    thresholds["duration_s"]["critical"],
                    thresholds["queries"]["warning"],
                    thresholds["queries"]["critical"],
                )
            )
            lines.append("")
            slow = sorted(tests, key=lambda t: t["duration_s"], reverse=True)[:5]
            lines.append("Slow tests (top 5):")
            for item in slow:
                lines.append(
                    f"- {item['name']} | {item['duration_s']:.4f}s | queries={item['queries']}"
                )
            lines.append("")

            heavy_queries = sorted(tests, key=lambda t: t["queries"], reverse=True)[:5]
            lines.append("Query-heavy tests (top 5):")
            for item in heavy_queries:
                lines.append(
                    f"- {item['name']} | queries={item['queries']} | {item['duration_s']:.4f}s"
                )
            lines.append("")

            lines.append("Pressure classification (threshold-based):")
            for item in tests:
                cls = item["classification"]
                lines.append(
                    f"- {item['name']} | level={cls['level']} | "
                    f"duration={item['duration_s']:.4f}s({cls['duration_level']}) "
                    f"queries={item['queries']}({cls['query_level']})"
                )
            lines.append("")

        if concurrency:
            lines.append("Concurrency outcomes:")
            for item in concurrency:
                reason_text = ",".join(item.get("reasons") or []) or "ok"
                lines.append(
                    f"- {item['name']} | attempts={item['attempts']} successes={item['successes']} "
                    f"errors={item['error_count']} | status={item['status']} | {reason_text}"
                )
                if item["error_types"]:
                    lines.append(f"  error_types={item['error_types']}")
                if item["note"]:
                    lines.append(f"  note={item['note']}")
            lines.append("")

        if metrics:
            lines.append("Custom metrics:")
            for item in metrics:
                unit = item["unit"] or ""
                unit_text = f" {unit}" if unit else ""
                lines.append(
                    f"- {item['name']} | {item['metric']}={item['value']}{unit_text} | extra={item['extra']}"
                )
            lines.append("")

        weak_points = []
        for item in tests:
            if item["classification"]["level"] != "good":
                weak_points.append(
                    f"{item['name']} (pressure-{item['classification']['level']})"
                )
        for item in concurrency:
            if item.get("level") != "good":
                weak_points.append(f"{item['name']} (concurrency-{item['status']})")

        if weak_points:
            lines.append("Weak points:")
            for entry in sorted(set(weak_points)):
                lines.append(f"- {entry}")
            lines.append("")

        if errors:
            lines.append("Errors:")
            for item in errors:
                lines.append(f"- {item['name']} | {item['error']}")
            lines.append("")

        return "\n".join(lines)

    def _write_json(self, path, payload):
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)

    def print_summary(self, output_path=None, force=False):
        with self._lock:
            if self._printed and not force:
                return
            self._printed = True
            snapshot = {
                "tests": list(self._tests),
                "concurrency": list(self._concurrency),
                "metrics": list(self._metrics),
                "errors": list(self._errors),
            }

        payload = self._build_payload(snapshot)
        summary = self._summarize(payload)
        payload["summary"] = summary
        print(summary)

        if output_path is None:
            output_path = os.getenv("PERF_REPORT_PATH")
            if not output_path and settings is not None:
                output_path = getattr(settings, "PERF_REPORT_PATH", None)
            if not output_path:
                output_path = os.path.join(os.getcwd(), "performance-report.json")

        try:
            self._write_json(str(output_path), payload)
            print(f"Performance report saved to: {output_path}")
        except OSError as exc:
            print(f"Performance report could not be saved: {exc}")


class PerformanceTestMixin:
    def setUp(self):
        super().setUp()
        self._perf_start = time.perf_counter()
        self._perf_queries_start = len(connection.queries)

    def tearDown(self):
        duration = time.perf_counter() - self._perf_start
        queries = len(connection.queries) - self._perf_queries_start
        PerformanceReport.instance().record_test(self.id(), duration, queries)
        super().tearDown()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        PerformanceReport.instance().print_summary()
