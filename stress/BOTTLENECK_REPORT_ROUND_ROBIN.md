# Bottleneck Analysis Report — Round-Robin Load Balancer (Requirement #10)

**Generated:** 2026-06-19 13:09 UTC

## Objective

Identify a measurable bottleneck on the **round-robin OpenResty** entry (`openresty-rr` on port **8090**)
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
openresty-rr :8090  ── plain round-robin ──► Django replicas
       │
       └── ~33% each: app_main | app_worker_1 | app_worker_2
```

## Bottleneck identified

**Hot read path:** `GET /api/products/{id}/`

Without caching, every product detail request executes a PostgreSQL query and
serializer work. Under load, this becomes a read amplification bottleneck on the DB.

**Optimization applied:** cache-aside in `app/product/catalog_cache.py` (`get_product_cached`).

## Measurement setup

| Parameter | Value |
|-----------|-------|
| Entry point | `http://localhost:8090` |
| Load balancer | **Round-robin (openresty-rr :8090)** |
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
| `product.get_product_cached` (500/501 calls) | 2.9 ms | 1.08 ms | 62.8% |

```json
{
  "before": {
    "count": 500,
    "mean_ms": 3.12,
    "median_ms": 2.9,
    "p95_ms": 4.13,
    "max_ms": 50.14
  },
  "after": {
    "count": 501,
    "mean_ms": 1.23,
    "median_ms": 1.08,
    "p95_ms": 2.23,
    "max_ms": 5.73
  }
}
```

## Concurrent HTTP latency

25 parallel workers hammering the same product through `http://localhost:8090`.

| Metric | BEFORE (no cache) | AFTER (Redis cache) | Improvement |
|--------|------------------:|--------------------:|------------:|
| Mean | 387.24 ms | 343.51 ms | 11.3% |
| Median | 309.59 ms | 274.53 ms | 11.3% |
| p95 | 933.97 ms | 800.19 ms | 14.3% |
| Min | 76.76 ms | 53.66 ms | — |
| Max | 1500.68 ms | 1530.06 ms | — |

### Routing during concurrent phase (`X-Served-By`)

- **BEFORE:** `{"app_worker_2": 167, "app_worker_1": 165, "app_main": 168}`
- **AFTER:** `{"app_worker_1": 167, "app_main": 166, "app_worker_2": 167}`

## Serial HTTP latency (single client — reference only)

One request at a time. Most time is spent outside Django (LB Lua, affinity, TCP).
Small cache wins are often invisible here.

| Metric | BEFORE (no cache) | AFTER (Redis cache) | Improvement |
|--------|------------------:|--------------------:|------------:|
| Mean | 41.43 ms | 41.78 ms | -0.8% |
| Median | 43.08 ms | 43.35 ms | -0.6% |
| p95 | 54.31 ms | 57.81 ms | -6.4% |
| Min | 20.74 ms | 21.53 ms | — |
| Max | 79.77 ms | 84.71 ms | — |

- **BEFORE routing:** `{"app_main": 66, "app_worker_1": 68, "app_worker_2": 66}`
- **AFTER routing:** `{"app_main": 68, "app_worker_1": 66, "app_worker_2": 66}`

## Secondary bottleneck (not optimized here)

`POST /api/invoices/create/` uses pessimistic row locks. Under high concurrency
this returns **HTTP 409** by design. Edge LB does not remove DB lock contention.

## Conclusion

Redis cache-aside **does** help at the service layer. Service-layer `get_product_cached` median improved **62.8%** (2.9 ms → 1.08 ms) and p95 by **46.0%** in-process. Through **round-robin LB**, concurrent HTTP median improved **11.3%** (309.59 ms → 274.53 ms); p95 improved **14.3%**. Serial single-client numbers can look flat for the same reason.

## Related reports

- [`BOTTLENECK_REPORT_CUSTOM_LB.md`](BOTTLENECK_REPORT_CUSTOM_LB.md) — same benchmark via custom LB
- [`BOTTLENECK_REPORT.md`](BOTTLENECK_REPORT.md) — early baseline (serial-only)
- [`REPORT_ROUND_ROBIN.md`](REPORT_ROUND_ROBIN.md) — 100-user stress via round-robin
- [`../docs/REDIS_CACHE_BEFORE_AFTER.md`](../docs/REDIS_CACHE_BEFORE_AFTER.md) — Redis impact on both LBs

## Re-run

```bash
python scripts/benchmark_bottleneck.py --lb round_robin -n 200 --concurrency 25 --concurrent-requests 500
```

## Implementation references

- `app/common/performance_monitor.py` — `@monitor_execution`
- `app/common/middleware.py` — `PerformanceMonitorMiddleware`
- `GET /api/performance/stats/`
- `app/product/catalog_cache.py` — cache-aside
- `docs/CUSTOM_LOAD_BALANCING.md` — custom LB design
