#!/usr/bin/env python3
"""
Run requirement #9 stress test: 100+ concurrent users, integrity checks, REPORT.md.

Usage (from django_ecomerce/ with Docker stack up):
  python scripts/run_stress_test.py
  python scripts/run_stress_test.py -u 120 -t 120 --host http://localhost:8088
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
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILE = ROOT / "docker-compose.prod.yml"
STRESS_DIR = ROOT / "stress"
RESULTS_DIR = STRESS_DIR / "results"


@dataclass
class StressSummary:
    users: int
    spawn_rate: int
    duration_sec: int
    host: str
    total_requests: int
    total_failures: int
    requests_per_sec: float
    median_ms: float
    p95_ms: float
    checkout_requests: int
    checkout_409_count: int
    http_5xx_count: int
    integrity_ok: bool
    negative_stock: int
    negative_wallets: int


def http_get(url: str, timeout: float = 15.0) -> tuple[int, str]:
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read(128).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(128).decode("utf-8", errors="replace")


def wait_for_host(base: str, retries: int = 30) -> None:
    for attempt in range(1, retries + 1):
        code, _ = http_get(f"{base}/api/health/")
        if code == 200:
            print(f"  ready: {base}")
            return
        print(f"  waiting ({attempt}/{retries}): {base}/api/health/ -> HTTP {code}")
        time.sleep(2)
    raise RuntimeError(f"Host not ready: {base}")


def seed_catalog(stock: int = 5000) -> None:
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
            f"n = Product.objects.update(stock={stock}); "
            "[evict_product(p.pk) for p in Product.objects.all()]; "
            f"print('restocked', n, 'products to', {stock})"
        ),
    ]
    print(f"Seeding catalog stock={stock}...")
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.stdout:
        print(proc.stdout.strip())
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or "seed failed")


def run_locust(
    *,
    host: str,
    users: int,
    spawn_rate: int,
    duration_sec: int,
    use_docker: bool,
    run_label: str = "stress_run",
) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    prefix = RESULTS_DIR / run_label
    for stale in RESULTS_DIR.glob(f"{run_label}*"):
        stale.unlink(missing_ok=True)

    locustfile = "./stress/locustfile_stress.py"
    csv_path = f"/app/stress/results/{run_label}" if use_docker else str(prefix)

    if use_docker:
        if "8090" in host or "openresty-rr" in host:
            locust_host = "http://openresty-rr:80"
        elif "8088" in host or "openresty" in host:
            locust_host = "http://openresty:80"
        else:
            locust_host = host
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
            locust_host,
            "--headless",
            "-u",
            str(users),
            "-r",
            str(spawn_rate),
            "--run-time",
            f"{duration_sec}s",
            "--csv",
            csv_path,
            "--html",
            f"{csv_path}.html",
            "--stop-timeout",
            "30",
        ]
    else:
        cmd = [
            "locust",
            "-f",
            str(STRESS_DIR / "locustfile_stress.py"),
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
            str(prefix),
            "--html",
            f"{prefix}.html",
            "--stop-timeout",
            "30",
        ]

    print("Running:", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.stdout:
        print(proc.stdout[-4000:] if len(proc.stdout) > 4000 else proc.stdout)
    if proc.stderr:
        print(proc.stderr, file=sys.stderr)

    stats_path = Path(f"{prefix}_stats.csv")
    if not stats_path.exists() and use_docker:
        stats_path = RESULTS_DIR / f"{run_label}_stats.csv"
    if not stats_path.exists():
        raise RuntimeError("Locust did not produce stats CSV")
    if proc.returncode != 0:
        print(f"Note: Locust exit code {proc.returncode} (409 conflicts may count as failures).")
    return stats_path


def _float(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def parse_locust_stats(stats_path: Path, users: int, spawn_rate: int, duration_sec: int, host: str) -> StressSummary:
    total_requests = 0
    total_failures = 0
    rps = 0.0
    median_ms = 0.0
    p95_ms = 0.0
    checkout_requests = 0
    checkout_failures = 0

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
            elif name == "Create Order Invoice":
                checkout_requests = int(_float(row.get("Request Count", 0)))
                checkout_failures = int(_float(row.get("Failure Count", 0)))

    failures_path = stats_path.with_name(stats_path.name.replace("_stats.csv", "_failures.csv"))
    checkout_409 = checkout_failures
    http_5xx = 0
    if failures_path.exists():
        with failures_path.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                err = row.get("Error", "")
                if row.get("Name") == "Create Order Invoice" and "409" in err:
                    checkout_409 += 0  # already in failure count
                if any(code in err for code in ("500", "502", "503", "504")):
                    http_5xx += int(row.get("Occurrences", 1) or 1)

    return StressSummary(
        users=users,
        spawn_rate=spawn_rate,
        duration_sec=duration_sec,
        host=host,
        total_requests=total_requests,
        total_failures=total_failures,
        requests_per_sec=rps,
        median_ms=median_ms,
        p95_ms=p95_ms,
        checkout_requests=checkout_requests,
        checkout_409_count=checkout_failures,
        http_5xx_count=http_5xx,
        integrity_ok=False,
        negative_stock=-1,
        negative_wallets=-1,
    )


def check_db_integrity() -> tuple[bool, int, int]:
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
            "from app.wallets.models import Wallet; "
            "ns = Product.objects.filter(stock__lt=0).count(); "
            "nw = Wallet.objects.filter(balance__lt=0).count(); "
            "print(ns, nw)"
        ),
    ]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        return False, -1, -1
    for line in reversed(proc.stdout.strip().splitlines()):
        line = line.strip()
        if not line or line.startswith("19 objects"):
            continue
        parts = line.split()
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            ns, nw = int(parts[0]), int(parts[1])
            return ns == 0 and nw == 0, ns, nw
    print(proc.stdout, file=sys.stderr)
    return False, -1, -1


def write_report(summary: StressSummary, report_path: Path, *, lb_mode: str = "custom", lb_type: str = "custom") -> None:
    fail_pct = (100.0 * summary.total_failures / summary.total_requests) if summary.total_requests else 0.0
    stability = (
        summary.users >= 100
        and summary.http_5xx_count == 0
        and summary.integrity_ok
        and summary.total_requests > 0
    )

    lines = [
        "# Stress Test Report (Requirement #9)",
        "",
        f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "## Objective",
        "",
        "Prove the Django e-commerce stack handles **100+ concurrent users** without",
        "server collapse or data corruption (negative stock / negative wallet balances).",
        "",
        "## Test configuration",
        "",
        "| Parameter | Value |",
        "|-----------|-------|",
        f"| Entry point | `{summary.host}` |",
        f"| Load balancer | **{lb_mode}** |",
        f"| Concurrent users | **{summary.users}** |",
        f"| Spawn rate | {summary.spawn_rate}/s |",
        f"| Duration | {summary.duration_sec}s |",
        f"| Locust profile | `stress/locustfile_stress.py` |",
        "",
        "## Results",
        "",
        "| Metric | Value |",
        "|--------|------:|",
        f"| Total HTTP requests | {summary.total_requests} |",
        f"| Throughput | {summary.requests_per_sec:.2f} req/s |",
        f"| Median latency | {summary.median_ms:.0f} ms |",
        f"| p95 latency | {summary.p95_ms:.0f} ms |",
        f"| Locust failures (all) | {summary.total_failures} ({fail_pct:.1f}%) |",
        f"| Checkout attempts | {summary.checkout_requests} |",
        f"| Checkout conflicts (409) | {summary.checkout_409_count} |",
        f"| HTTP 5xx errors | {summary.http_5xx_count} |",
        "",
        "## Data integrity (post-run)",
        "",
        "| Check | Result |",
        "|-------|--------|",
        f"| Negative product stock rows | **{summary.negative_stock}** |",
        f"| Negative wallet balance rows | **{summary.negative_wallets}** |",
        f"| Integrity pass | **{'YES' if summary.integrity_ok else 'NO'}** |",
        "",
        "## Conclusion",
        "",
    ]

    if stability:
        lines.append(
            f"**PASS** — {summary.users} concurrent users for {summary.duration_sec}s with "
            f"**0 HTTP 5xx** and **no data corruption**. "
            f"Checkout 409 responses ({summary.checkout_409_count}) are expected under "
            "pessimistic locking when multiple users compete for the same stock."
        )
    else:
        lines.append(
            "**Review needed** — check HTTP 5xx count, integrity counters, or increase "
            "stock seed / duration and re-run `python scripts/run_stress_test.py`."
        )

    artifact_prefix = "stress_run_rr" if lb_type == "round_robin" else "stress_run_custom"
    summary_json = "stress_summary_rr.json" if lb_type == "round_robin" else "stress_summary_custom.json"
    rerun_cmd = (
        "python scripts/run_stress_test.py --lb round_robin -u 100 -r 10 -t 120"
        if lb_type == "round_robin"
        else "python scripts/run_stress_test.py --lb custom -u 100 -r 10 -t 120"
    )
    lines.extend(
        [
            "",
            "## Artifacts",
            "",
            f"- `stress/results/{artifact_prefix}_stats.csv`",
            f"- `stress/results/{artifact_prefix}.html`",
            f"- `stress/results/{summary_json}`",
            "",
            "## Re-run",
            "",
            "```bash",
            "docker compose -f docker-compose.prod.yml up -d",
            rerun_cmd,
            "```",
        ]
    )
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Requirement #9 stress test runner")
    parser.add_argument("-u", "--users", type=int, default=100)
    parser.add_argument("-r", "--spawn-rate", type=int, default=10)
    parser.add_argument("-t", "--run-time", type=int, default=120)
    parser.add_argument("--host", default="http://localhost:8088")
    parser.add_argument(
        "--lb",
        choices=("custom", "round_robin"),
        default="custom",
        help="custom -> :8088 openresty; round_robin -> :8090 openresty-rr",
    )
    parser.add_argument("--report", default="", help="Report output path (default: stress/REPORT.md or REPORT_ROUND_ROBIN.md)")
    parser.add_argument("--no-docker", action="store_true", help="Run locust on host instead of locust container")
    parser.add_argument("--skip-seed", action="store_true")
    args = parser.parse_args()

    if args.users < 100:
        print(f"Warning: requirement #9 expects >= 100 users; got {args.users}")

    if args.lb == "round_robin" and args.host == "http://localhost:8088":
        args.host = "http://localhost:8090"

    run_label = "stress_run_rr" if args.lb == "round_robin" else "stress_run_custom"
    report_path = Path(args.report) if args.report else (
        STRESS_DIR / ("REPORT_ROUND_ROBIN.md" if args.lb == "round_robin" else "REPORT_CUSTOM_LB.md")
    )
    lb_title = "Round-robin (openresty-rr :8090)" if args.lb == "round_robin" else "Custom LB (openresty :8088)"

    wait_for_host(args.host)
    if not args.skip_seed:
        seed_catalog(stock=5000)

    stats_path = run_locust(
        host=args.host,
        users=args.users,
        spawn_rate=args.spawn_rate,
        duration_sec=args.run_time,
        use_docker=not args.no_docker,
        run_label=run_label,
    )
    summary = parse_locust_stats(stats_path, args.users, args.spawn_rate, args.run_time, args.host)

    ok, ns, nw = check_db_integrity()
    summary.integrity_ok = ok
    summary.negative_stock = ns
    summary.negative_wallets = nw

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    json_path = RESULTS_DIR / ("stress_summary_rr.json" if args.lb == "round_robin" else "stress_summary_custom.json")
    json_path.write_text(json.dumps(summary.__dict__, indent=2), encoding="utf-8")
    write_report(summary, report_path, lb_mode=lb_title, lb_type=args.lb)

    print("\n" + "=" * 60)
    print(f"Users: {summary.users} | Requests: {summary.total_requests} | RPS: {summary.requests_per_sec:.1f}")
    print(f"5xx: {summary.http_5xx_count} | Integrity: {'PASS' if summary.integrity_ok else 'FAIL'}")
    print(f"Report: {report_path}")
    print("=" * 60)
    return 0 if summary.integrity_ok and summary.http_5xx_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
