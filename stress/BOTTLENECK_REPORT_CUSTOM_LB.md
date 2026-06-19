# Bottleneck Analysis Report — Custom Load Balancer (Requirement #10)

**Generated:** 2026-06-19 13:05 UTC

## Objective

Identify a measurable bottleneck on the **custom OpenResty load balancer** entry
and document numeric **before/after** improvement after applying Redis cache-aside.

This report uses three views:

1. **Service-layer** (`@monitor_execution`) — isolates cache vs PostgreSQL inside Django
2. **Concurrent HTTP** — parallel readers where DB read amplification appears
3. **Serial HTTP** — single client; often dominated by LB/network overhead

## Architecture under test

```
Client (benchmark script)
       │
       ▼
openresty :8088  ── affinity + P2C + Redis live state ──► Django replicas
       │
       └── X-Served-By: app_main | app_worker_1 | app_worker_2
```

## Bottleneck identified

**Hot read path:** `GET /api/products/{id}/`

Without caching, every product detail request executes a PostgreSQL query and
serializer work. Under load, this becomes a read amplification bottleneck on the DB.

**Optimization applied:** cache-aside in `app/product/catalog_cache.py` (`get_product_cached`).

## Measurement setup

| Parameter | Value |
|-----------|-------|
| Entry point | `http://localhost:8088` |
| Load balancer | **Custom LB (openresty :8088)** |
| Product ID | 16 |
| Serial samples per phase | 200 |
| Concurrent requests per phase | 500 |
| Concurrent workers | 25 |
| BEFORE | Header `X-Bypass-Product-Cache: 1` (PostgreSQL every request) |
| AFTER | Normal cache-aside (one warm miss, then Redis hits) |

Service-layer timings are measured in-process (`manage.py shell` on `app_main`) so
all samples land in one Python process — not fragmented across Gunicorn workers.

## Service-layer comparison (in-process, sequential)

`product.get_product_cached` via `@monitor_execution` in one Django process —
isolates cache vs PostgreSQL without LB noise or Gunicorn worker fragmentation.

| Layer | BEFORE median | AFTER median | Improvement |
|-------|-------------:|-------------:|------------:|
| `product.get_product_cached` (500/501 calls) | 2.75 ms | 1.0 ms | 63.6% |

```json
{
  "before": {
    "count": 500,
    "mean_ms": 3.07,
    "median_ms": 2.75,
    "p95_ms": 4.23,
    "max_ms": 49.17
  },
  "after": {
    "count": 501,
    "mean_ms": 1.16,
    "median_ms": 1.0,
    "p95_ms": 2.06,
    "max_ms": 14.92
  }
}
```

## Concurrent HTTP latency

25 parallel workers hammering the same product through `http://localhost:8088`.

| Metric | BEFORE (no cache) | AFTER (Redis cache) | Improvement |
|--------|------------------:|--------------------:|------------:|
| Mean | 311.73 ms | 287.17 ms | 7.9% |
| Median | 289.57 ms | 266.52 ms | 8.0% |
| p95 | 549.1 ms | 518.71 ms | 5.5% |
| Min | 78.08 ms | 38.04 ms | — |
| Max | 698.43 ms | 687.38 ms | — |

### Routing during concurrent phase (`X-Served-By`)

- **BEFORE:** `{"app_worker_1": 495, "app_worker_2": 5}`
- **AFTER:** `{"app_worker_1": 500}`

## Serial HTTP latency (single client — reference only)

One request at a time. Most time is spent outside Django (LB Lua, affinity, TCP).
Small cache wins are often invisible here.

| Metric | BEFORE (no cache) | AFTER (Redis cache) | Improvement |
|--------|------------------:|--------------------:|------------:|
| Mean | 37.91 ms | 36.64 ms | 3.4% |
| Median | 37.6 ms | 34.63 ms | 7.9% |
| p95 | 52.23 ms | 50.69 ms | 2.9% |
| Min | 15.5 ms | 15.39 ms | — |
| Max | 60.95 ms | 109.35 ms | — |

- **BEFORE routing:** `{"app_worker_1": 200}`
- **AFTER routing:** `{"app_worker_1": 200}`

## Secondary bottleneck (not optimized here)

`POST /api/invoices/create/` uses pessimistic row locks. Under high concurrency
this returns **HTTP 409** by design. Edge LB does not remove DB lock contention.

## Conclusion

Redis cache-aside **does** help at the service layer. Service-layer `get_product_cached` median improved **63.6%** (2.75 ms → 1.0 ms) and p95 by **51.3%** in-process. Through **custom LB**, concurrent HTTP median improved **8.0%** (289.57 ms → 266.52 ms); p95 improved **5.5%**. Serial single-client numbers can look flat for the same reason.

## Related reports

- [`BOTTLENECK_REPORT_ROUND_ROBIN.md`](BOTTLENECK_REPORT_ROUND_ROBIN.md) — same benchmark via round-robin
- [`BOTTLENECK_REPORT.md`](BOTTLENECK_REPORT.md) — early baseline (serial-only)
- [`REPORT_CUSTOM_LB.md`](REPORT_CUSTOM_LB.md) — 100-user stress via custom LB
- [`../docs/REDIS_CACHE_BEFORE_AFTER.md`](../docs/REDIS_CACHE_BEFORE_AFTER.md) — Redis impact on both LBs

## Re-run

```bash
python scripts/benchmark_bottleneck.py --lb custom -n 200 --concurrency 25 --concurrent-requests 500
```

## Implementation references

- `app/common/performance_monitor.py` — `@monitor_execution`
- `app/common/middleware.py` — `PerformanceMonitorMiddleware`
- `GET /api/performance/stats/`
- `app/product/catalog_cache.py` — cache-aside
- `docs/CUSTOM_LOAD_BALANCING.md` — custom LB design
