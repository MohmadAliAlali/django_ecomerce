#!/usr/bin/env python3
"""Fair A/B benchmark: custom OpenResty LB vs round-robin baseline.

Runs identical headless Locust scenarios against both entry points inside Docker,
then prints a side-by-side summary (throughput, latency, HTTP errors, checkout 409s).
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILE = ROOT / "docker-compose.prod.yml"
RESULTS_DIR = ROOT / "benchmark_results"

SCENARIOS = (
    {
        "label": "custom_lb",
        "title": "Custom LB (:8088 / openresty)",
        "host": "http://openresty:80",
        "public_base": "http://localhost:8088",
    },
    {
        "label": "round_robin",
        "title": "Round-robin (:8090 / openresty-rr)",
        "host": "http://openresty-rr:80",
        "public_base": "http://localhost:8090",
    },
)


@dataclass
class RunSummary:
    label: str
    title: str
    users: int
    spawn_rate: int
    duration_sec: int
    total_requests: int
    total_failures: int
    requests_per_sec: float
    median_ms: float
    p95_ms: float
    avg_ms: float
    checkout_requests: int
    checkout_failures: int
    checkout_median_ms: float
    checkout_p95_ms: float
    product_list_median_ms: float
    product_list_p95_ms: float
    aggregated_fail_pct: float


def http_get(url: str, timeout: float = 10.0) -> tuple[int, str]:
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read(256).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(256).decode("utf-8", errors="replace")


def wait_for_stack(bases: list[str], retries: int = 30, delay_sec: float = 2.0) -> None:
    pending = list(bases)
    for attempt in range(1, retries + 1):
        still_pending = []
        for base in pending:
            code, _ = http_get(f"{base}/api/products/")
            if code == 200:
                print(f"  ready: {base}")
            else:
                still_pending.append(base)
                print(f"  waiting ({attempt}/{retries}): {base} -> HTTP {code}")
        pending = still_pending
        if not pending:
            return
        time.sleep(delay_sec)
    raise RuntimeError(f"Stack not ready: {pending}")


def reset_catalog_stock(stock: int = 500) -> None:
    """Restore product stock so both LB runs start from the same inventory."""
    cmd = [
        "docker",
        "compose",
        "-f",
        str(COMPOSE_FILE),
        "exec",
        "-T",
        "app_main",
        "python",
        "manage.py",
        "shell",
        "-c",
        (
            "from app.product.models import Product; "
            "from app.product.catalog_cache import evict_product; "
            f"updated = Product.objects.update(stock={stock}); "
            "[evict_product(p.pk) for p in Product.objects.all()]; "
            f"print('restocked', updated, 'products to', {stock})"
        ),
    ]
    print(f"\nResetting product stock to {stock} before next scenario...")
    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.stdout:
        print(proc.stdout.strip())
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        raise RuntimeError("Failed to reset product stock between benchmark runs")


def run_locust(
    *,
    label: str,
    host: str,
    users: int,
    spawn_rate: int,
    duration_sec: int,
    locustfile: str = "./e_commerce/locustfile.py",
) -> Path:
    out_prefix = RESULTS_DIR / label
    out_prefix.parent.mkdir(parents=True, exist_ok=True)
    for stale in out_prefix.parent.glob(f"{label}*"):
        stale.unlink(missing_ok=True)

    cmd = [
        "docker",
        "compose",
        "-f",
        str(COMPOSE_FILE),
        "exec",
        "-T",
        "locust",
        "locust",
        "-f",
        locustfile,
        "--host",
        host,
        "--headless",
        "-u",
        str(users),
        "-r",
        str(spawn_rate),
        "--run-time",
        f"{duration_sec}s",
        "--csv",
        f"/app/benchmark_results/{label}",
        "--html",
        f"/app/benchmark_results/{label}.html",
        "--stop-timeout",
        "20",
    ]
    print(f"\n=== Running {label} ===")
    print(" ".join(cmd))
    started = time.time()
    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    elapsed = time.time() - started
    if proc.stdout:
        try:
            print(proc.stdout)
        except UnicodeEncodeError:
            print(proc.stdout.encode("ascii", errors="replace").decode("ascii"))
    if proc.stderr:
        print(proc.stderr, file=sys.stderr)
    stats_path = Path(f"{out_prefix}_stats.csv")
    if proc.returncode != 0 and not stats_path.exists():
        raise RuntimeError(f"Locust run failed for {label} (exit {proc.returncode})")
    if proc.returncode != 0:
        print(f"Note: Locust exit code {proc.returncode} (expected when checkout 409s occur).")
    print(f"Completed in {elapsed:.1f}s")
    return out_prefix


def _float(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def parse_stats(prefix: Path, meta: dict, users: int, spawn_rate: int, duration_sec: int) -> RunSummary:
    stats_path = Path(f"{prefix}_stats.csv")
    failures_path = Path(f"{prefix}_failures.csv")
    if not stats_path.exists():
        raise FileNotFoundError(stats_path)

    total_requests = 0
    total_failures = 0
    rps = 0.0
    median_ms = 0.0
    p95_ms = 0.0
    avg_ms = 0.0
    checkout_requests = 0
    checkout_failures = 0
    checkout_median_ms = 0.0
    checkout_p95_ms = 0.0
    product_list_median_ms = 0.0
    product_list_p95_ms = 0.0

    with stats_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            name = row.get("Name", "")
            if name == "Aggregated":
                total_requests = int(_float(row.get("Request Count", 0)))
                total_failures = int(_float(row.get("Failure Count", 0)))
                rps = _float(row.get("Requests/s", 0))
                median_ms = _float(row.get("Median Response Time", 0))
                p95_ms = _float(row.get("95%", 0))
                avg_ms = _float(row.get("Average Response Time", 0))
            elif name == "Create Order Invoice":
                checkout_requests = int(_float(row.get("Request Count", 0)))
                checkout_failures = int(_float(row.get("Failure Count", 0)))
                checkout_median_ms = _float(row.get("Median Response Time", 0))
                checkout_p95_ms = _float(row.get("95%", 0))
            elif name == "Get Product List":
                product_list_median_ms = _float(row.get("Median Response Time", 0))
                product_list_p95_ms = _float(row.get("95%", 0))

    checkout_409_estimate = checkout_failures
    if failures_path.exists():
        with failures_path.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            checkout_409_estimate = sum(
                1
                for row in reader
                if row.get("Name") == "Create Order Invoice" and "409" in row.get("Error", "")
            )

    fail_pct = (100.0 * total_failures / total_requests) if total_requests else 0.0
    return RunSummary(
        label=meta["label"],
        title=meta["title"],
        users=users,
        spawn_rate=spawn_rate,
        duration_sec=duration_sec,
        total_requests=total_requests,
        total_failures=total_failures,
        requests_per_sec=rps,
        median_ms=median_ms,
        p95_ms=p95_ms,
        avg_ms=avg_ms,
        checkout_requests=checkout_requests,
        checkout_failures=checkout_409_estimate,
        checkout_median_ms=checkout_median_ms,
        checkout_p95_ms=checkout_p95_ms,
        product_list_median_ms=product_list_median_ms,
        product_list_p95_ms=product_list_p95_ms,
        aggregated_fail_pct=fail_pct,
    )


def print_comparison(summaries: list[RunSummary]) -> None:
    if len(summaries) != 2:
        return
    custom, rr = summaries
    print("\n" + "=" * 72)
    print("FAIR A/B RESULTS (identical Locust profile)")
    print("=" * 72)
    print(f"Users: {custom.users} | Spawn rate: {custom.spawn_rate}/s | Duration: {custom.duration_sec}s")
    print()
    headers = ("Metric", custom.title, rr.title, "Delta (custom - RR)")
    rows = [
        ("Total requests", str(custom.total_requests), str(rr.total_requests), f"{custom.total_requests - rr.total_requests:+d}"),
        ("Throughput (req/s)", f"{custom.requests_per_sec:.2f}", f"{rr.requests_per_sec:.2f}", f"{custom.requests_per_sec - rr.requests_per_sec:+.2f}"),
        ("Median latency (ms)", f"{custom.median_ms:.0f}", f"{rr.median_ms:.0f}", f"{custom.median_ms - rr.median_ms:+.0f}"),
        ("p95 latency (ms)", f"{custom.p95_ms:.0f}", f"{rr.p95_ms:.0f}", f"{custom.p95_ms - rr.p95_ms:+.0f}"),
        ("Avg latency (ms)", f"{custom.avg_ms:.0f}", f"{rr.avg_ms:.0f}", f"{custom.avg_ms - rr.avg_ms:+.0f}"),
        ("Locust failures (all)", str(custom.total_failures), str(rr.total_failures), f"{custom.total_failures - rr.total_failures:+d}"),
        ("Locust fail %", f"{custom.aggregated_fail_pct:.1f}%", f"{rr.aggregated_fail_pct:.1f}%", f"{custom.aggregated_fail_pct - rr.aggregated_fail_pct:+.1f}pp"),
        ("Checkout attempts", str(custom.checkout_requests), str(rr.checkout_requests), f"{custom.checkout_requests - rr.checkout_requests:+d}"),
        ("Checkout failures (409+)", str(custom.checkout_failures), str(rr.checkout_failures), f"{custom.checkout_failures - rr.checkout_failures:+d}"),
        ("Checkout median (ms)", f"{custom.checkout_median_ms:.0f}", f"{rr.checkout_median_ms:.0f}", f"{custom.checkout_median_ms - rr.checkout_median_ms:+.0f}"),
        ("Checkout p95 (ms)", f"{custom.checkout_p95_ms:.0f}", f"{rr.checkout_p95_ms:.0f}", f"{custom.checkout_p95_ms - rr.checkout_p95_ms:+.0f}"),
        ("Product list median (ms)", f"{custom.product_list_median_ms:.0f}", f"{rr.product_list_median_ms:.0f}", f"{custom.product_list_median_ms - rr.product_list_median_ms:+.0f}"),
        ("Product list p95 (ms)", f"{custom.product_list_p95_ms:.0f}", f"{rr.product_list_p95_ms:.0f}", f"{custom.product_list_p95_ms - rr.product_list_p95_ms:+.0f}"),
    ]
    col_widths = [max(len(row[i]) for row in ([headers] + rows)) for i in range(4)]
    for row in [headers, *rows]:
        print("  ".join(cell.ljust(col_widths[i]) for i, cell in enumerate(row)))

    throughput_win = custom.requests_per_sec > rr.requests_per_sec
    latency_win = custom.median_ms < rr.median_ms
    print()
    if throughput_win and latency_win:
        print("Verdict: Custom LB shows higher throughput AND lower median latency in this run.")
    elif throughput_win:
        print("Verdict: Custom LB shows higher throughput; median latency is mixed or worse.")
    elif latency_win:
        print("Verdict: Custom LB shows lower median latency; throughput is mixed or worse.")
    else:
        print("Verdict: Round-robin matched or beat custom LB on throughput and median latency.")
    print("Note: Locust counts checkout 409 as failures; those are expected under stock contention.")
    print(f"Reports: {RESULTS_DIR}")


def write_json_report(summaries: list[RunSummary], path: Path) -> None:
    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "runs": [summary.__dict__ for summary in summaries],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fair custom LB vs round-robin Locust benchmark")
    parser.add_argument("-u", "--users", type=int, default=50)
    parser.add_argument("-r", "--spawn-rate", type=int, default=5)
    parser.add_argument("-t", "--run-time", type=int, default=90, help="Duration per scenario (seconds)")
    parser.add_argument("--cooldown", type=int, default=15, help="Pause between scenarios (seconds)")
    parser.add_argument("--locustfile", default="./e_commerce/locustfile.py")
    parser.add_argument("--results-prefix", default="", help="Optional prefix for CSV/HTML output labels")
    parser.add_argument("--skip-wait", action="store_true")
    args = parser.parse_args()

    print("Waiting for both load balancers...")
    if not args.skip_wait:
        wait_for_stack([s["public_base"] for s in SCENARIOS])

    reset_catalog_stock()

    summaries: list[RunSummary] = []
    for idx, scenario in enumerate(SCENARIOS):
        label = f"{args.results_prefix}{scenario['label']}" if args.results_prefix else scenario["label"]
        if idx > 0:
            reset_catalog_stock()
            if args.cooldown > 0:
                print(f"Cooldown {args.cooldown}s before {label}...")
                time.sleep(args.cooldown)
        prefix = run_locust(
            label=label,
            host=scenario["host"],
            users=args.users,
            spawn_rate=args.spawn_rate,
            duration_sec=args.run_time,
            locustfile=args.locustfile,
        )
        summaries.append(
            parse_stats(prefix, scenario, args.users, args.spawn_rate, args.run_time)
        )

    print_comparison(summaries)
    report_path = RESULTS_DIR / "ab_summary.json"
    write_json_report(summaries, report_path)
    print(f"JSON summary: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
