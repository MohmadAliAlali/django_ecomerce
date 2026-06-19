# Bottleneck Analysis Report (Requirement #10)

**Generated:** 2026-06-19 12:45 UTC

## Objective

Identify a measurable bottleneck and document numeric **before/after** improvement.
This mirrors Spring Boot's `PerformanceMonitorAspect` (AOP execution timing) combined
with a concrete optimization: **Redis cache-aside for product detail reads** (req #6).

## Bottleneck identified

**Hot read path:** `GET /api/products/{id}/`

Without caching, every product detail request executes a PostgreSQL query and
serializer work. Under load, this becomes a read amplification bottleneck on the DB.

**Optimization applied:** cache-aside in `app/product/catalog_cache.py` (`get_product_cached`).

## Measurement setup

| Parameter | Value |
|-----------|-------|
| Host | `http://localhost:8088` |
| Product ID | 16 |
| Samples per phase | 200 |
| BEFORE | Header `X-Bypass-Product-Cache: 1` (PostgreSQL every request) |
| AFTER | Normal cache-aside (one warm miss, then Redis hits) |

## HTTP latency comparison

| Metric | BEFORE (no cache) | AFTER (Redis cache) | Improvement |
|--------|------------------:|--------------------:|------------:|
| Mean | 38.6 ms | 31.97 ms | 17.2% |
| Median | 38.67 ms | 30.82 ms | 20.3% |
| p95 | 53.04 ms | 49.87 ms | 6.0% |
| Min | 16.16 ms | 14.93 ms | — |
| Max | 116.17 ms | 56.69 ms | — |

## Service-layer timings (AOP equivalent)

Django `@monitor_execution` on service functions + `PerformanceMonitorMiddleware`
for `/api/*` requests. Snapshot after benchmark:

```json
{
  "product.get_product_cached": {
    "count": 58,
    "mean_ms": 2.26,
    "median_ms": 1.07,
    "p95_ms": 3.65,
    "max_ms": 36.08
  },
  "http.GET./api/products/16/": {
    "count": 58,
    "mean_ms": 3.72,
    "median_ms": 2.75,
    "p95_ms": 6.12,
    "max_ms": 41.66
  }
}
```

Key monitored paths (mirrors Spring `core.service.*`):

- `product.get_product_cached` — catalog read service
- `invoices.checkout` — transactional checkout
- `product.adjust_stock` — optimistic stock adjustment

## Secondary bottleneck (not optimized here)

`POST /api/invoices/create/` uses pessimistic row locks (`select_for_update`) on
wallet and product rows. Under high concurrency this correctly returns **HTTP 409**
for conflicts — a data integrity feature, not an LB issue. Further scaling would
require queue-based checkout or inventory partitioning, not edge routing alone.

## Conclusion

Distributed product cache reduced median read latency by **20.3%** (38.67 ms → 30.82 ms) and p95 by **6.0%** in this run. The monitoring layer confirms where time is spent and validates the optimization target.

## Re-run

```bash
python scripts/benchmark_bottleneck.py --host http://localhost:8088 -n 300
```

## Implementation references

- `app/common/performance_monitor.py` — `@monitor_execution` decorator
- `app/common/middleware.py` — `PerformanceMonitorMiddleware`
- `GET /api/performance/stats/` — aggregated timings
- `app/product/catalog_cache.py` — cache-aside optimization
