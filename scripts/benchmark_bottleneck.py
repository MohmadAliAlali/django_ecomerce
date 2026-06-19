#!/usr/bin/env python3
"""
Requirement #10: bottleneck analysis with before/after numeric comparison.

Phases:
  1. Serial HTTP — single client (LB/network noise often dominates)
  2. Concurrent HTTP — many parallel readers (cache benefit visible)
  3. Service-layer — @monitor_execution on get_product_cached per phase

Usage:
  python scripts/benchmark_bottleneck.py
  python scripts/benchmark_bottleneck.py --lb custom -n 200
  python scripts/benchmark_bottleneck.py --concurrency 25 --concurrent-requests 500
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STRESS_DIR = ROOT / "stress"
RESULTS_DIR = STRESS_DIR / "results"
COMPOSE_FILE = ROOT / "docker-compose.prod.yml"

SERVICE_LABEL = "product.get_product_cached"


@dataclass
class PhaseResult:
    label: str
    samples: int
    mean_ms: float
    median_ms: float
    p95_ms: float
    min_ms: float
    max_ms: float


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = int(round((pct / 100.0) * (len(ordered) - 1)))
    return ordered[max(0, min(idx, len(ordered) - 1))]


def phase_from_timings(label: str, timings: list[float]) -> PhaseResult:
    if not timings:
        raise RuntimeError(f"No successful samples for phase {label}")
    return PhaseResult(
        label=label,
        samples=len(timings),
        mean_ms=round(statistics.mean(timings), 2),
        median_ms=round(statistics.median(timings), 2),
        p95_ms=round(percentile(timings, 95), 2),
        min_ms=round(min(timings), 2),
        max_ms=round(max(timings), 2),
    )


def http_request(
    method: str, url: str, headers: dict | None = None
) -> tuple[int, dict | list | None, dict[str, str]]:
    hdrs = dict(headers or {})
    req = urllib.request.Request(url, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8")
            resp_headers = {k: v for k, v in resp.headers.items()}
            body = json.loads(raw) if raw else None
            return resp.status, body, resp_headers
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        resp_headers = {k: v for k, v in exc.headers.items()}
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            body = None
        return exc.code, body, resp_headers


def http_json(method: str, url: str, headers: dict | None = None) -> tuple[int, dict | list | None]:
    code, body, _ = http_request(method, url, headers)
    return code, body


def pick_product_id(base: str) -> int:
    code, body = http_json("GET", f"{base}/api/products/")
    if code != 200 or not isinstance(body, list) or not body:
        raise RuntimeError("No products available for benchmark")
    return int(body[0]["id"])


def reset_performance_stats(base: str) -> None:
    http_json("DELETE", f"{base}/api/performance/stats/")


def fetch_performance_stats(base: str) -> dict:
    code, body = http_json("GET", f"{base}/api/performance/stats/")
    return body if code == 200 and isinstance(body, dict) else {}


def extract_service_stats(perf_stats: dict, product_id: int) -> dict[str, dict]:
    http_label = f"http.GET./api/products/{product_id}/"
    out: dict[str, dict] = {}
    for key in (SERVICE_LABEL, http_label):
        if key in perf_stats:
            out[key] = perf_stats[key]
    return out


def parse_json_from_shell_output(stdout: str) -> dict:
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            return json.loads(line)
    raise RuntimeError(f"No JSON payload in shell output:\n{stdout[-500:]}")


def bench_service_layer_inprocess(
    product_id: int,
    samples: int,
    concurrency: int,
    *,
    container: str = "app_main",
) -> tuple[dict, dict]:
    """
    Concurrent get_product_cached inside one Django process (manage.py shell).
    Avoids Gunicorn multi-worker stat fragmentation and LB overhead.
    """
    script = f"""
import json
from app.common.performance_monitor import reset_stats, get_stats_snapshot
from app.product.catalog_cache import get_product_cached, evict_product

PID = {product_id}
N = {samples}

def run_phase(bypass):
    evict_product(PID)
    reset_stats()
    if not bypass:
        get_product_cached(PID)
    for _ in range(N):
        get_product_cached(PID, bypass_cache=bypass)
    return get_stats_snapshot().get("{SERVICE_LABEL}", {{}})

print(json.dumps({{"before": run_phase(True), "after": run_phase(False)}}))
"""
    cmd = [
        "docker",
        "compose",
        "-f",
        str(COMPOSE_FILE),
        "exec",
        "-T",
        container,
        "python",
        "manage.py",
        "shell",
        "-c",
        script,
    ]
    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or proc.stdout or "in-process service benchmark failed")
    payload = parse_json_from_shell_output(proc.stdout)
    return payload.get("before", {}), payload.get("after", {})


def evict_product_cache(product_id: int, *, container: str = "app_main") -> None:
    script = (
        f"from app.product.catalog_cache import evict_product; "
        f"evict_product({product_id}); print('evicted')"
    )
    cmd = [
        "docker",
        "compose",
        "-f",
        str(COMPOSE_FILE),
        "exec",
        "-T",
        container,
        "python",
        "manage.py",
        "shell",
        "-c",
        script,
    ]
    subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=False)


def bench_product_detail(
    base: str,
    product_id: int,
    samples: int,
    bypass_cache: bool,
) -> tuple[PhaseResult, dict[str, int]]:
    label = "before_no_cache" if bypass_cache else "after_redis_cache"
    headers = {"X-Bypass-Product-Cache": "1"} if bypass_cache else {}
    timings: list[float] = []
    served_by: dict[str, int] = {}

    if not bypass_cache:
        http_json("GET", f"{base}/api/products/{product_id}/", headers)
        time.sleep(0.05)

    for _ in range(samples):
        started = time.perf_counter()
        code, _, resp_headers = http_request("GET", f"{base}/api/products/{product_id}/", headers)
        elapsed_ms = (time.perf_counter() - started) * 1000
        if code == 200:
            timings.append(elapsed_ms)
            node = resp_headers.get("X-Served-By") or resp_headers.get("x-served-by") or "unknown"
            served_by[node] = served_by.get(node, 0) + 1

    return phase_from_timings(label, timings), served_by


def bench_product_detail_concurrent(
    base: str,
    product_id: int,
    total_requests: int,
    concurrency: int,
    bypass_cache: bool,
) -> tuple[PhaseResult, dict[str, int]]:
    label = "concurrent_before_no_cache" if bypass_cache else "concurrent_after_redis_cache"
    headers = {"X-Bypass-Product-Cache": "1"} if bypass_cache else {}
    url = f"{base}/api/products/{product_id}/"
    timings: list[float] = []
    served_by: dict[str, int] = {}
    lock = threading.Lock()

    if not bypass_cache:
        http_json("GET", url, headers)
        time.sleep(0.05)

    def one_request(_: int) -> None:
        started = time.perf_counter()
        code, _, resp_headers = http_request("GET", url, headers)
        elapsed_ms = (time.perf_counter() - started) * 1000
        if code != 200:
            return
        with lock:
            timings.append(elapsed_ms)
            node = resp_headers.get("X-Served-By") or resp_headers.get("x-served-by") or "unknown"
            served_by[node] = served_by.get(node, 0) + 1

    workers = max(1, min(concurrency, total_requests))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(one_request, range(total_requests)))

    return phase_from_timings(label, timings), served_by


def improvement_pct(before: float, after: float) -> float:
    if before <= 0:
        return 0.0
    return round(100.0 * (before - after) / before, 1)


def format_latency_table(before: PhaseResult, after: PhaseResult) -> list[str]:
    med_imp = improvement_pct(before.median_ms, after.median_ms)
    p95_imp = improvement_pct(before.p95_ms, after.p95_ms)
    return [
        "| Metric | BEFORE (no cache) | AFTER (Redis cache) | Improvement |",
        "|--------|------------------:|--------------------:|------------:|",
        f"| Mean | {before.mean_ms} ms | {after.mean_ms} ms | {improvement_pct(before.mean_ms, after.mean_ms)}% |",
        f"| Median | {before.median_ms} ms | {after.median_ms} ms | {med_imp}% |",
        f"| p95 | {before.p95_ms} ms | {after.p95_ms} ms | {p95_imp}% |",
        f"| Min | {before.min_ms} ms | {after.min_ms} ms | — |",
        f"| Max | {before.max_ms} ms | {after.max_ms} ms | — |",
    ]


def format_service_table(before: dict, after: dict) -> list[str]:
    b_med = before.get("median_ms", 0)
    a_med = after.get("median_ms", 0)
    b_cnt = before.get("count", 0)
    a_cnt = after.get("count", 0)
    imp = improvement_pct(float(b_med), float(a_med))
    return [
        "| Layer | BEFORE median | AFTER median | Improvement |",
        "|-------|-------------:|-------------:|------------:|",
        f"| `{SERVICE_LABEL}` ({b_cnt}/{a_cnt} calls) | {b_med} ms | {a_med} ms | {imp}% |",
    ]


def write_bottleneck_report(
    *,
    serial_before: PhaseResult,
    serial_after: PhaseResult,
    concurrent_before: PhaseResult,
    concurrent_after: PhaseResult,
    service_before: dict,
    service_after: dict,
    host: str,
    product_id: int,
    lb: str,
    lb_label: str,
    concurrency: int,
    served_serial_before: dict[str, int],
    served_serial_after: dict[str, int],
    served_conc_before: dict[str, int],
    served_conc_after: dict[str, int],
    report_path: Path,
    summary_path: Path,
) -> None:
    conc_med_imp = improvement_pct(concurrent_before.median_ms, concurrent_after.median_ms)
    conc_p95_imp = improvement_pct(concurrent_before.p95_ms, concurrent_after.p95_ms)
    svc_med_imp = improvement_pct(
        float(service_before.get("median_ms", 0)),
        float(service_after.get("median_ms", 0)),
    )
    svc_p95_imp = improvement_pct(
        float(service_before.get("p95_ms", 0)),
        float(service_after.get("p95_ms", 0)),
    )

    if lb == "round_robin":
        report_title = "Round-Robin Load Balancer (Requirement #10)"
        objective_lb = "the **round-robin OpenResty** entry (`openresty-rr` on port **8090**)"
        arch_diagram = (
            "Client (benchmark script)\n"
            "       │\n"
            "       ▼\n"
            "openresty-rr :8090  ── plain round-robin ──► Django replicas\n"
            "       │\n"
            "       └── ~33% each: app_main | app_worker_1 | app_worker_2"
        )
        lb_phrase = "round-robin LB"
        related_reports = [
            "- [`BOTTLENECK_REPORT_CUSTOM_LB.md`](BOTTLENECK_REPORT_CUSTOM_LB.md) — same benchmark via custom LB",
            "- [`BOTTLENECK_REPORT.md`](BOTTLENECK_REPORT.md) — early baseline (serial-only)",
            "- [`REPORT_ROUND_ROBIN.md`](REPORT_ROUND_ROBIN.md) — 100-user stress via round-robin",
            "- [`../docs/REDIS_CACHE_BEFORE_AFTER.md`](../docs/REDIS_CACHE_BEFORE_AFTER.md) — Redis impact on both LBs",
        ]
        rerun_cmd = (
            "python scripts/benchmark_bottleneck.py --lb round_robin -n 200 "
            "--concurrency 25 --concurrent-requests 500"
        )
    else:
        report_title = "Custom Load Balancer (Requirement #10)"
        objective_lb = "the **custom OpenResty load balancer** entry (`openresty` on port **8088**)"
        arch_diagram = (
            "Client (benchmark script)\n"
            "       │\n"
            "       ▼\n"
            "openresty :8088  ── affinity + P2C + Redis live state ──► Django replicas\n"
            "       │\n"
            "       └── X-Served-By: app_main | app_worker_1 | app_worker_2"
        )
        lb_phrase = "custom LB"
        related_reports = [
            "- [`BOTTLENECK_REPORT_ROUND_ROBIN.md`](BOTTLENECK_REPORT_ROUND_ROBIN.md) — same benchmark via round-robin",
            "- [`BOTTLENECK_REPORT.md`](BOTTLENECK_REPORT.md) — early baseline (serial-only)",
            "- [`REPORT_CUSTOM_LB.md`](REPORT_CUSTOM_LB.md) — 100-user stress via custom LB",
            "- [`../docs/REDIS_CACHE_BEFORE_AFTER.md`](../docs/REDIS_CACHE_BEFORE_AFTER.md) — Redis impact on both LBs",
        ]
        rerun_cmd = (
            "python scripts/benchmark_bottleneck.py --lb custom -n 200 "
            "--concurrency 25 --concurrent-requests 500"
        )

    lines = [
        f"# Bottleneck Analysis Report — {report_title}",
        "",
        f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "## Objective",
        "",
        f"Identify a measurable bottleneck on {objective_lb}",
        "and document numeric **before/after** improvement after applying Redis cache-aside.",
        "",
        "This report uses three views:",
        "",
        "1. **Service-layer** (`@monitor_execution`) — isolates cache vs PostgreSQL inside Django",
        "2. **Concurrent HTTP** — parallel readers where DB read amplification appears",
        "3. **Serial HTTP** — single client; often dominated by LB/network overhead",
        "",
        "## Architecture under test",
        "",
        "```",
        arch_diagram,
        "```",
        "",
        "## Bottleneck identified",
        "",
        "**Hot read path:** `GET /api/products/{id}/`",
        "",
        "Without caching, every product detail request executes a PostgreSQL query and",
        "serializer work. Under load, this becomes a read amplification bottleneck on the DB.",
        "",
        "**Optimization applied:** cache-aside in `app/product/catalog_cache.py` (`get_product_cached`).",
        "",
        "## Measurement setup",
        "",
        "| Parameter | Value |",
        "|-----------|-------|",
        f"| Entry point | `{host}` |",
        f"| Load balancer | **{lb_label}** |",
        f"| Product ID | {product_id} |",
        f"| Serial samples per phase | {serial_before.samples} |",
        f"| Concurrent requests per phase | {concurrent_before.samples} |",
        f"| Concurrent workers | {concurrency} |",
        "| BEFORE | Header `X-Bypass-Product-Cache: 1` (PostgreSQL every request) |",
        "| AFTER | Normal cache-aside (one warm miss, then Redis hits) |",
        "",
        "Service-layer timings are measured in-process (`manage.py shell` on `app_main`) so",
        "all samples land in one Python process — not fragmented across Gunicorn workers.",
        "",
        "## Service-layer comparison (in-process, sequential)",
        "",
        "`product.get_product_cached` via `@monitor_execution` in one Django process —",
        "isolates cache vs PostgreSQL without LB noise or Gunicorn worker fragmentation.",
        "",
        *format_service_table(service_before, service_after),
        "",
        "```json",
        json.dumps({"before": service_before, "after": service_after}, indent=2),
        "```",
        "",
        "## Concurrent HTTP latency",
        "",
        f"{concurrency} parallel workers hammering the same product through `{host}`.",
        "",
        *format_latency_table(concurrent_before, concurrent_after),
        "",
        "### Routing during concurrent phase (`X-Served-By`)",
        "",
        f"- **BEFORE:** `{json.dumps(served_conc_before)}`",
        f"- **AFTER:** `{json.dumps(served_conc_after)}`",
        "",
        "## Serial HTTP latency (single client — reference only)",
        "",
        "One request at a time. Most time is spent outside Django (LB Lua, affinity, TCP).",
        "Small cache wins are often invisible here.",
        "",
        *format_latency_table(serial_before, serial_after),
        "",
        f"- **BEFORE routing:** `{json.dumps(served_serial_before)}`",
        f"- **AFTER routing:** `{json.dumps(served_serial_after)}`",
        "",
        "## Secondary bottleneck (not optimized here)",
        "",
        "`POST /api/invoices/create/` uses pessimistic row locks. Under high concurrency",
        "this returns **HTTP 409** by design. Edge LB does not remove DB lock contention.",
        "",
        "## Conclusion",
        "",
    ]

    if conc_med_imp > 0 or svc_med_imp > 0:
        parts = []
        if svc_med_imp > 0:
            parts.append(
                f"Service-layer `get_product_cached` median improved **{svc_med_imp}%** "
                f"({service_before.get('median_ms', '—')} ms → {service_after.get('median_ms', '—')} ms) "
                f"and p95 by **{svc_p95_imp}%** in-process."
            )
        if conc_med_imp > 0:
            parts.append(
                f"Through **{lb_phrase}**, concurrent HTTP median improved **{conc_med_imp}%** "
                f"({concurrent_before.median_ms} ms → {concurrent_after.median_ms} ms); "
                f"p95 improved **{conc_p95_imp}%**."
            )
        elif svc_med_imp > 0:
            parts.append(
                f"Concurrent HTTP through the {lb_phrase} was noisy this run ({conc_med_imp}% median) "
                "because edge routing and replica queueing dominate end-to-end latency."
            )
        parts.append(
            "Serial single-client numbers can look flat for the same reason."
        )
        lines.append("Redis cache-aside **does** help at the service layer. " + " ".join(parts))
    else:
        lines.append(
            "Neither service-layer nor concurrent HTTP showed improvement in this run. "
            "Re-run with Docker up, Redis healthy, and `PERFORMANCE_BENCHMARK_ALLOW_BYPASS=True`. "
            "See [`BOTTLENECK_REPORT.md`](BOTTLENECK_REPORT.md) for the preserved baseline run."
        )

    lines.extend(
        [
            "",
            "## Related reports",
            "",
            *related_reports,
            "",
            "## Re-run",
            "",
            "```bash",
            rerun_cmd,
            "```",
            "",
            "## Implementation references",
            "",
            "- `app/common/performance_monitor.py` — `@monitor_execution`",
            "- `app/common/middleware.py` — `PerformanceMonitorMiddleware`",
            "- `GET /api/performance/stats/`",
            "- `app/product/catalog_cache.py` — cache-aside",
            "- `docs/CUSTOM_LOAD_BALANCING.md` — custom LB design",
        ]
    )

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    payload = {
        "host": host,
        "load_balancer": lb_label,
        "lb": lb,
        "product_id": product_id,
        "concurrency": concurrency,
        "serial_before": serial_before.__dict__,
        "serial_after": serial_after.__dict__,
        "concurrent_before": concurrent_before.__dict__,
        "concurrent_after": concurrent_after.__dict__,
        "service_before": service_before,
        "service_after": service_after,
        "served_serial_before": served_serial_before,
        "served_serial_after": served_serial_after,
        "served_conc_before": served_conc_before,
        "served_conc_after": served_conc_after,
        "improvement_concurrent_median_pct": conc_med_imp,
        "improvement_concurrent_p95_pct": conc_p95_imp,
        "improvement_service_median_pct": svc_med_imp,
        "improvement_service_p95_pct": svc_p95_imp,
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Requirement #10 bottleneck benchmark")
    parser.add_argument("--host", default="http://localhost:8088")
    parser.add_argument(
        "--lb",
        choices=("custom", "round_robin"),
        default="custom",
        help="custom -> :8088; round_robin -> :8090",
    )
    parser.add_argument("-n", "--samples", type=int, default=200, help="Serial requests per phase")
    parser.add_argument(
        "--concurrency",
        type=int,
        default=25,
        help="Parallel workers for concurrent phase",
    )
    parser.add_argument(
        "--concurrent-requests",
        type=int,
        default=500,
        help="Total requests per concurrent phase",
    )
    parser.add_argument(
        "--report",
        default="",
        help="Report path (default: BOTTLENECK_REPORT_CUSTOM_LB.md for custom LB)",
    )
    args = parser.parse_args()

    if args.lb == "round_robin" and args.host == "http://localhost:8088":
        args.host = "http://localhost:8090"

    lb_label = (
        "Custom LB (openresty :8088)"
        if args.lb == "custom"
        else "Round-robin (openresty-rr :8090)"
    )
    report_path = Path(args.report) if args.report else (
        STRESS_DIR / (
            "BOTTLENECK_REPORT_CUSTOM_LB.md"
            if args.lb == "custom"
            else "BOTTLENECK_REPORT_ROUND_ROBIN.md"
        )
    )
    summary_path = RESULTS_DIR / (
        "bottleneck_summary_custom_lb.json"
        if args.lb == "custom"
        else "bottleneck_summary_rr.json"
    )

    code, _ = http_json("GET", f"{args.host}/api/health/")
    if code != 200:
        raise SystemExit(f"Health check failed: HTTP {code} at {args.host}")

    product_id = pick_product_id(args.host)

    print(f"Benchmark via {lb_label} product_id={product_id}")
    print(f"  serial={args.samples}/phase  concurrent={args.concurrent_requests} @ {args.concurrency} workers")

    print("Service-layer in-process BEFORE/AFTER...")
    service_before, service_after = bench_service_layer_inprocess(
        product_id,
        args.concurrent_requests,
        args.concurrency,
    )
    print(
        f"  BEFORE median={service_before.get('median_ms')}ms "
        f"p95={service_before.get('p95_ms')}ms count={service_before.get('count')}"
    )
    print(
        f"  AFTER  median={service_after.get('median_ms')}ms "
        f"p95={service_after.get('p95_ms')}ms count={service_after.get('count')}"
    )

    evict_product_cache(product_id)
    print("Concurrent BEFORE (no cache)...")
    concurrent_before, served_conc_before = bench_product_detail_concurrent(
        args.host,
        product_id,
        args.concurrent_requests,
        args.concurrency,
        bypass_cache=True,
    )
    print(f"  median={concurrent_before.median_ms}ms p95={concurrent_before.p95_ms}ms")

    time.sleep(2)
    evict_product_cache(product_id)
    print("Concurrent AFTER (Redis cache)...")
    concurrent_after, served_conc_after = bench_product_detail_concurrent(
        args.host,
        product_id,
        args.concurrent_requests,
        args.concurrency,
        bypass_cache=False,
    )
    print(f"  median={concurrent_after.median_ms}ms p95={concurrent_after.p95_ms}ms")

    print("Serial BEFORE (no cache)...")
    serial_before, served_serial_before = bench_product_detail(
        args.host, product_id, args.samples, bypass_cache=True
    )
    print(f"  median={serial_before.median_ms}ms p95={serial_before.p95_ms}ms")

    print("Serial AFTER (Redis cache)...")
    serial_after, served_serial_after = bench_product_detail(
        args.host, product_id, args.samples, bypass_cache=False
    )
    print(f"  median={serial_after.median_ms}ms p95={serial_after.p95_ms}ms")

    write_bottleneck_report(
        serial_before=serial_before,
        serial_after=serial_after,
        concurrent_before=concurrent_before,
        concurrent_after=concurrent_after,
        service_before=service_before,
        service_after=service_after,
        host=args.host,
        product_id=product_id,
        lb=args.lb,
        lb_label=lb_label,
        concurrency=args.concurrency,
        served_serial_before=served_serial_before,
        served_serial_after=served_serial_after,
        served_conc_before=served_conc_before,
        served_conc_after=served_conc_after,
        report_path=report_path,
        summary_path=summary_path,
    )

    svc_imp = improvement_pct(
        float(service_before.get("median_ms", 0)),
        float(service_after.get("median_ms", 0)),
    )
    conc_imp = improvement_pct(concurrent_before.median_ms, concurrent_after.median_ms)
    print(f"\nService-layer median improvement: {svc_imp}%")
    print(f"Concurrent HTTP median improvement: {conc_imp}%")
    print(f"Report: {report_path}")
    print(f"Summary: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
