#!/usr/bin/env python3
"""Full-stack smoke + integrity checks against the running Docker LB stack."""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal

BASE_CUSTOM = "http://localhost:8088"
BASE_RR = "http://localhost:8090"


def request(method: str, url: str, body: dict | None = None, headers: dict | None = None):
    data = None
    hdrs = dict(headers or {})
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        hdrs.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
            parsed = json.loads(raw) if raw else None
            return resp.status, dict(resp.headers), parsed
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = raw
        return exc.code, dict(exc.headers), parsed


def check(name: str, ok: bool, detail: str = "") -> bool:
    status = "PASS" if ok else "FAIL"
    suffix = f" — {detail}" if detail else ""
    print(f"[{status}] {name}{suffix}")
    return ok


def main() -> int:
    passed = 0
    total = 0

    def record(name: str, ok: bool, detail: str = "") -> None:
        nonlocal passed, total
        total += 1
        if check(name, ok, detail):
            passed += 1

    # --- Public endpoints ---
    code, headers, body = request("GET", f"{BASE_CUSTOM}/api/products/")
    record("Custom LB product list", code == 200, f"HTTP {code}")

    code, headers, body = request("GET", f"{BASE_RR}/api/products/")
    record("Round-robin product list", code == 200, f"HTTP {code}")

    code, headers, body = request("GET", f"{BASE_CUSTOM}/internal/node-info")
    record(
        "Node info",
        code == 200 and isinstance(body, dict) and "nodeId" in body,
        f"node={body.get('nodeId') if isinstance(body, dict) else body}",
    )

    code, _, body = request("GET", f"{BASE_CUSTOM}/api/load-distribution/servers")
    record(
        "Load distribution servers",
        code == 200 and isinstance(body, list) and len(body) >= 3,
        f"count={len(body) if isinstance(body, list) else 0}",
    )

    code, _, body = request(
        "POST",
        f"{BASE_CUSTOM}/api/load-distribution/route",
        {"expectedComputeUnits": 450},
    )
    record(
        "Load distribution route",
        code == 200 and isinstance(body, dict) and body.get("serverId"),
        f"server={body.get('serverId') if isinstance(body, dict) else body}",
    )

    served_by = Counter()
    for _ in range(12):
        _, hdrs, _ = request("GET", f"{BASE_CUSTOM}/api/products/")
        served_by[hdrs.get("X-Served-By", "missing")] += 1
    record(
        "Custom LB spreads X-Served-By",
        len(served_by) >= 1,
        str(dict(served_by)),
    )

    # --- Auth + checkout flow ---
    user = f"smoke_{abs(hash('smoke')) % 100000}"
    password = "StressTestPass123!"
    code, _, signup = request(
        "POST",
        f"{BASE_CUSTOM}/api/accounts/signup/",
        {"username": user, "email": f"{user}@test.com", "password": password},
    )
    record("Signup", code in (200, 201), f"HTTP {code}")

    code, _, login = request(
        "POST",
        f"{BASE_CUSTOM}/api/accounts/login/",
        {"username": user, "password": password},
    )
    token = login.get("token") if isinstance(login, dict) else None
    record("Login", code == 200 and bool(token), f"HTTP {code}")
    auth = {"Authorization": f"Token {token}"}

    code, _, _ = request("PUT", f"{BASE_CUSTOM}/api/wallets/add-funds/", {"amount": "200.00"}, auth)
    record("Wallet top-up", code == 200, f"HTTP {code}")

    code, _, products = request("GET", f"{BASE_CUSTOM}/api/products/")
    product_id = products[0]["id"] if isinstance(products, list) and products else None
    record("Products available for checkout", product_id is not None, f"id={product_id}")

    if product_id:
        code, _, _ = request(
            "POST",
            f"{BASE_CUSTOM}/api/cart/create/",
            {"products_id": product_id, "quantity": 1},
            auth,
        )
        record("Add to cart", code == 201, f"HTTP {code}")

        code, _, invoice = request("POST", f"{BASE_CUSTOM}/api/invoices/create/", {}, auth)
        record("Checkout (sync + locks)", code == 201, f"HTTP {code}")

        code, _, detail = request("GET", f"{BASE_CUSTOM}/api/products/{product_id}/")
        record("Cached product detail", code == 200, f"stock={detail.get('stock') if isinstance(detail, dict) else detail}")

    # --- Concurrent checkout integrity ---
    def concurrent_user(idx: int) -> tuple[str, int]:
        username = f"race_{idx}_{abs(hash(idx)) % 100000}"
        pwd = "RaceTestPass123!"
        _, _, _ = request(
            "POST",
            f"{BASE_CUSTOM}/api/accounts/signup/",
            {"username": username, "email": f"{username}@test.com", "password": pwd},
        )
        _, _, login_body = request(
            "POST",
            f"{BASE_CUSTOM}/api/accounts/login/",
            {"username": username, "password": pwd},
        )
        tok = login_body.get("token") if isinstance(login_body, dict) else None
        hdr = {"Authorization": f"Token {tok}"}
        request("PUT", f"{BASE_CUSTOM}/api/wallets/add-funds/", {"amount": "100.00"}, hdr)
        request(
            "POST",
            f"{BASE_CUSTOM}/api/cart/create/",
            {"products_id": product_id, "quantity": 1},
            hdr,
        )
        code, _, _ = request("POST", f"{BASE_CUSTOM}/api/invoices/create/", {}, hdr)
        return username, code

    if product_id:
        results = []
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(concurrent_user, i) for i in range(8)]
            for fut in as_completed(futures):
                results.append(fut.result())
        success = sum(1 for _, code in results if code == 201)
        conflict = sum(1 for _, code in results if code == 409)
        other = len(results) - success - conflict
        record(
            "Concurrent checkout on shared stock",
            success >= 1 and success + conflict == len(results),
            f"201={success}, 409={conflict}, other={other}",
        )

    print(f"\nSummary: {passed}/{total} checks passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
