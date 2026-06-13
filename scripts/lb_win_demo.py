#!/usr/bin/env python3
"""Demonstrate custom LB winning under checkout-heavy load + one throttled replica."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILE = ROOT / "docker-compose.prod.yml"
COMPOSE_DEMO = ROOT / "docker-compose.demo.yml"
SERVERS_JSON = ROOT / "scripts" / "servers.django.json"
RESULTS_DIR = ROOT / "benchmark_results"

sys.path.insert(0, str(ROOT / "scripts"))
from lb_ab_benchmark import (  # noqa: E402
    SCENARIOS,
    print_comparison,
    reset_catalog_stock,
    run_locust,
    parse_stats,
    wait_for_stack,
    write_json_report,
)


def http_json(method: str, url: str, body: dict | None = None, headers: dict | None = None):
    data = None
    hdrs = dict(headers or {})
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        hdrs.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = resp.read().decode("utf-8")
        return resp.status, dict(resp.headers), json.loads(raw) if raw else None


def compose_cmd(*args: str) -> list[str]:
    cmd = ["docker", "compose", "-f", str(COMPOSE_FILE), "-f", str(COMPOSE_DEMO)]
    cmd.extend(args)
    return cmd


def run_compose(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        compose_cmd(*args),
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        raise RuntimeError(f"docker compose failed: {' '.join(args)}")
    return proc


def prepare_demo_routing() -> str:
    """Balance worker_1/worker_2 capability so custom LB spreads load, not single-node hot spot."""
    original = SERVERS_JSON.read_text(encoding="utf-8")
    data = json.loads(original)
    for server in data.get("servers", []):
        if server.get("id") == "app_worker_2":
            server["weight"] = 1.0
            server["capabilityOverride"] = 5200
    SERVERS_JSON.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print("Patched servers.django.json for demo balance (worker_2 weight=1.0, cap=5200)")
    run_compose("restart", "decision-cache", "openresty")
    time.sleep(8)
    return original


def restore_servers_json(original: str) -> None:
    SERVERS_JSON.write_text(original, encoding="utf-8")
    run_compose("restart", "decision-cache", "openresty", check=False)
    print("Restored servers.django.json")


def ensure_slow_node(delay_ms: int = 1200) -> None:
    print(f"\nRecreating app_main with ARTIFICIAL_DELAY_MS={delay_ms} (demo overlay)...")
    proc = run_compose("up", "-d", "--force-recreate", "--no-deps", "app_main")
    if proc.stdout:
        print(proc.stdout.strip())
    time.sleep(6)


def verify_throttled_node(delay_ms: int) -> None:
    samples = []
    attempts = 0
    while len(samples) < 8 and attempts < 40:
        attempts += 1
        req = urllib.request.Request("http://localhost:8090/api/products/", method="GET")
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                served_by = resp.headers.get("X-Served-By", "")
                elapsed_ms = (time.perf_counter() - started) * 1000
                if served_by == "app_main" and resp.status == 200:
                    samples.append(elapsed_ms)
        except urllib.error.HTTPError:
            pass
    if not samples:
        raise RuntimeError("Could not sample throttled app_main via round-robin")
    median = sorted(samples)[len(samples) // 2]
    print(f"  RR hits to app_main: median={median:.0f}ms (delay target={delay_ms}ms, n={len(samples)})")
    if median < delay_ms * 0.6:
        raise RuntimeError("app_main throttling is too weak for demo")


def sample_served_by(base: str, path: str, headers: dict | None, samples: int = 50) -> Counter:
    counts: Counter = Counter()
    for _ in range(samples):
        req = urllib.request.Request(f"{base}{path}", headers=headers or {}, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                counts[resp.headers.get("X-Served-By", "missing")] += 1
        except urllib.error.HTTPError as exc:
            counts[exc.headers.get("X-Served-By", f"http-{exc.code}")] += 1
    return counts


def create_auth_headers(base: str) -> dict:
    user = f"route_probe_{int(time.time())}"
    password = "RouteProbePass123!"
    http_json(
        "POST",
        f"{base}/api/accounts/signup/",
        {"username": user, "email": f"{user}@test.com", "password": password},
    )
    _, _, login = http_json(
        "POST",
        f"{base}/api/accounts/login/",
        {"username": user, "password": password},
    )
    token = login.get("token") if isinstance(login, dict) else None
    if not token:
        raise RuntimeError("Failed to create probe user for routing samples")
    return {"Authorization": f"Token {token}"}


def print_routing_samples(base: str) -> None:
    print("\nRouting samples on custom LB (X-Served-By):")
    light = sample_served_by(base, "/api/products/", None, samples=60)
    auth = create_auth_headers(base)
    heavy = sample_served_by(base, "/api/wallets/my-wallet/", auth, samples=60)
    print(f"  Light reads (/api/products/): {dict(light)}")
    print(f"  Medium reads (/api/wallets/my-wallet/): {dict(heavy)}")
    slow_share_light = light.get("app_main", 0) / max(sum(light.values()), 1)
    slow_share_heavy = heavy.get("app_main", 0) / max(sum(heavy.values()), 1)
    print(f"  app_main share — light: {slow_share_light:.0%}, medium/heavy-ish: {slow_share_heavy:.0%}")


def print_win_verdict(custom, rr) -> None:
    print("\n" + "=" * 72)
    print("CHECKOUT-HEAVY + THROTTLED app_main — TARGET METRICS")
    print("=" * 72)
    metrics = [
        ("Checkout p95 (ms)", custom.checkout_p95_ms, rr.checkout_p95_ms, True),
        ("Checkout median (ms)", custom.checkout_median_ms, rr.checkout_median_ms, True),
        ("Product list p95 (ms)", custom.product_list_p95_ms, rr.product_list_p95_ms, True),
        ("Product list median (ms)", custom.product_list_median_ms, rr.product_list_median_ms, True),
        ("Throughput (req/s)", custom.requests_per_sec, rr.requests_per_sec, False),
    ]
    wins = 0
    for name, custom_val, rr_val, lower_is_better in metrics:
        if lower_is_better:
            winner = "custom" if custom_val < rr_val else ("rr" if rr_val < custom_val else "tie")
        else:
            winner = "custom" if custom_val > rr_val else ("rr" if rr_val > custom_val else "tie")
        if winner == "custom":
            wins += 1
        delta = custom_val - rr_val
        print(f"  {name}: custom={custom_val:.0f}  rr={rr_val:.0f}  delta={delta:+.0f}  -> {winner}")

    print()
    if custom.checkout_p95_ms < rr.checkout_p95_ms and custom.product_list_p95_ms <= rr.product_list_p95_ms * 1.05:
        print("Verdict: Custom LB is a clear win — lower checkout tail latency while keeping reads healthy.")
    elif wins >= 3:
        print("Verdict: Custom LB wins most target metrics in this scenario.")
    else:
        print("Verdict: Custom LB did not clearly win; check throttling, stock, or run duration.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Checkout-heavy LB win demonstration")
    parser.add_argument("-u", "--users", type=int, default=40)
    parser.add_argument("-r", "--spawn-rate", type=int, default=5)
    parser.add_argument("-t", "--run-time", type=int, default=90)
    parser.add_argument("--cooldown", type=int, default=15)
    parser.add_argument("--delay-ms", type=int, default=1200)
    parser.add_argument("--skip-restart", action="store_true")
    args = parser.parse_args()

    original_json = ""
    try:
        if not args.skip_restart:
            original_json = prepare_demo_routing()
            ensure_slow_node(args.delay_ms)

        wait_for_stack([s["public_base"] for s in SCENARIOS])
        verify_throttled_node(args.delay_ms)
        print_routing_samples(SCENARIOS[0]["public_base"])

        reset_catalog_stock(stock=1000)

        summaries = []
        locustfile = "./e_commerce/locustfile_checkout_heavy.py"
        for idx, scenario in enumerate(SCENARIOS):
            label = f"win_demo_{scenario['label']}"
            if idx > 0:
                reset_catalog_stock(stock=1000)
                if args.cooldown > 0:
                    print(f"Cooldown {args.cooldown}s before {label}...")
                    time.sleep(args.cooldown)
            prefix = run_locust(
                label=label,
                host=scenario["host"],
                users=args.users,
                spawn_rate=args.spawn_rate,
                duration_sec=args.run_time,
                locustfile=locustfile,
            )
            summaries.append(parse_stats(prefix, scenario, args.users, args.spawn_rate, args.run_time))

        print_comparison(summaries)
        print_win_verdict(summaries[0], summaries[1])

        report_path = RESULTS_DIR / "win_demo_summary.json"
        payload = {
            "scenario": "checkout_heavy_throttled_app_main",
            "artificial_delay_ms": args.delay_ms,
            "locustfile": locustfile,
            "runs": [summary.__dict__ for summary in summaries],
        }
        report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"JSON summary: {report_path}")
        return 0
    finally:
        if original_json:
            restore_servers_json(original_json)


if __name__ == "__main__":
    raise SystemExit(main())
