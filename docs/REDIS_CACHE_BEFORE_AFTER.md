# Redis Cache-Aside: Before/After Impact (Requirements #6 & #10)

This document explains **how Redis product caching changed the Django e-commerce stack**, with measured **before/after** numbers on **both entry points**:

| Entry | Port | Load balancer |
|-------|------|---------------|
| Custom LB | **8088** | OpenResty + Lua (affinity, P2C, live Redis node state) |
| Round-robin | **8090** | Plain nginx round-robin across 3 Gunicorn replicas |

Full report index: [`stress/index.md`](../stress/index.md).

---

## 1. What Redis does in this project

**Course requirement #6** — distributed cache-aside for hot catalog reads.

| Layer | Implementation |
|-------|----------------|
| Cache store | Redis (shared across all Django replicas) |
| Pattern | Cache-aside in `app/product/catalog_cache.py` |
| Hot path | `GET /api/products/{id}/` → `get_product_cached()` |
| TTL | 300 s (configurable via `PRODUCT_CACHE_TTL`) |
| Invalidation | `evict_product()` on stock/catalog writes |

### Before (no cache)

Every product detail request:

1. `Product.objects.get(pk=…)` — PostgreSQL round-trip
2. `ProductItemSerializer` — ORM → JSON
3. Response through Gunicorn → load balancer → client

Under concurrent readers this creates **read amplification** on PostgreSQL (connection pool pressure, repeated identical queries).

### After (Redis cache-aside)

1. `cache.get('product:{id}')` — Redis hit → return serialized dict (**~1 ms** in-process)
2. On miss: load from DB once, `cache.set(...)`, return

PostgreSQL is hit only on **cache miss** or **eviction**, not on every browse.

---

## 2. How we measure before vs after

Script: [`scripts/benchmark_bottleneck.py`](../scripts/benchmark_bottleneck.py)

| Phase | Method | What it proves |
|-------|--------|----------------|
| **BEFORE** | Header `X-Bypass-Product-Cache: 1` | Forces PostgreSQL on every request (controlled baseline) |
| **AFTER** | Normal `get_product_cached()` | One warm miss, then Redis hits |

Three views per load balancer:

| View | Description | Why it matters |
|------|-------------|----------------|
| **Service-layer** | 500 sequential calls in one Django process (`manage.py shell`) | Pure cache vs DB — no LB noise, no Gunicorn worker fragmentation |
| **Concurrent HTTP** | 25 workers × 500 requests through `:8088` or `:8090` | Shows cache benefit when many clients hit the same product |
| **Serial HTTP** | 200 sequential requests, one client | Reference only — LB/TCP overhead often hides small cache wins |

Service-layer numbers are **identical in mechanism** for both LBs (same Redis, same PostgreSQL). HTTP numbers differ because routing differs.

---

## 3. Measured improvements — side by side

**Product ID 16 · 500 concurrent samples · 25 workers · generated 2026-06-19**

### 3.1 Service layer (`product.get_product_cached`)

Measured in-process on `app_main` — **independent of load balancer choice**.

| Metric | BEFORE (PostgreSQL) | AFTER (Redis) | Improvement |
|--------|--------------------:|--------------:|------------:|
| Median | ~2.8 ms | ~1.0 ms | **~63%** |
| p95 | ~4.2 ms | ~2.1 ms | **~49%** |

Redis cuts catalog read time inside Django by roughly **two thirds** on the hot path.

### 3.2 Concurrent HTTP (25 parallel workers)

End-to-end latency through each load balancer entry:

| Metric | Custom LB `:8088` | | Round-robin `:8090` | |
|--------|------------------:|--:|---------------------:|--:|
| | BEFORE | AFTER | BEFORE | AFTER |
| **Median** | 289.6 ms | 266.5 ms | 309.6 ms | 274.5 ms |
| **Improvement** | | **8.0%** | | **11.3%** |
| **p95** | 549.1 ms | 518.7 ms | 934.0 ms | 800.2 ms |
| **Improvement** | | **5.5%** | | **14.3%** |

**Round-robin concurrent p95 improved more** in this run because traffic was spread evenly (~33% per replica) while the custom LB affinity-steered most product reads to one replica (`app_worker_1`). Both LBs benefit from cache; RR showed a larger tail-latency drop when the DB was bypassed under parallel load.

### 3.3 Serial HTTP (single client — reference)

| Metric | Custom LB | | Round-robin | |
|--------|----------:|--:|------------:|--:|
| | BEFORE | AFTER | BEFORE | AFTER |
| **Median** | 37.6 ms | 34.6 ms (**7.9%**) | 43.1 ms | 43.4 ms (~flat) |

Single-client latency is dominated by OpenResty (custom) or nginx (RR) plus TCP — not PostgreSQL. Small cache wins are often invisible here. **Do not use serial HTTP alone to judge cache value.**

### 3.4 Summary comparison table

| Measurement | Custom LB improvement | Round-robin improvement | Winner (this run) |
|-------------|----------------------:|------------------------:|-------------------|
| Service median | **63.6%** | **62.8%** | Tie (same Redis) |
| Service p95 | **51.3%** | **46.0%** | Tie |
| Concurrent HTTP median | **8.0%** | **11.3%** | Round-robin |
| Concurrent HTTP p95 | **5.5%** | **14.3%** | Round-robin |
| Serial HTTP median | **7.9%** | ~0% (noise) | Custom LB (marginal) |

**Takeaway:** Redis helps **both** load balancers. The service layer proves the optimization works; concurrent HTTP proves it survives real parallel load through the edge. Round-robin showed slightly higher concurrent gains in this run; custom LB still wins on overall 100-user throughput (see stress reports below).

---

## 4. Redis + load balancing under full stress (cache ON)

The **100-user Locust stress tests** run with **Redis cache enabled** (production path). They measure overall system behavior — not cache bypass.

| Metric | Custom LB `:8088` | Round-robin `:8090` | Custom vs RR |
|--------|------------------:|--------------------:|-------------:|
| Total requests (120 s) | **3,561** | 2,158 | **+65%** |
| Throughput | **28.9 req/s** | 17.9 req/s | **+61%** |
| Median latency | **750 ms** | 1,600 ms | **−53%** |
| p95 latency | **14,000 ms** | 28,000 ms | **−50%** |
| Failures / 5xx | **0** | **0** | Both PASS |
| Data integrity | **PASS** | **PASS** | Both PASS |

Product detail tasks in the Locust profile (`weight=3`) use the cached path. Redis reduces DB read load so replicas spend capacity on checkout, cart, and wallet work — especially important when the custom LB routes heavy writes to appropriate tiers.

Reports: [`REPORT_CUSTOM_LB.md`](../stress/REPORT_CUSTOM_LB.md) · [`REPORT_ROUND_ROBIN.md`](../stress/REPORT_ROUND_ROBIN.md)

---

## 5. How Redis affects the whole architecture

```
                    ┌─────────────────────────────────────┐
                    │           Locust / Clients            │
                    └─────────────────┬───────────────────┘
                                      │
              ┌───────────────────────┴───────────────────────┐
              ▼                                               ▼
     openresty :8088                                  openresty-rr :8090
     (custom LB)                                      (round-robin)
              │                                               │
              └───────────────────────┬───────────────────────┘
                                      ▼
                         Django replicas (×3 Gunicorn)
                                      │
                    ┌─────────────────┴─────────────────┐
                    ▼                                   ▼
              PostgreSQL                            Redis
              (writes, cache miss,                  (product:{id}
               checkout locks)                       cache hits)
```

| Without Redis | With Redis |
|---------------|------------|
| Every product view hits PostgreSQL | Most product views hit Redis |
| Read amplification under browse-heavy load | DB protected; pool free for checkout |
| Higher replica CPU on identical SELECTs | Lower DB latency; better tail latency under stress |
| LB only distributes load | LB + cache **compound** — less work per replica |

Redis does **not** remove checkout lock contention (`POST /api/invoices/create/` still uses `select_for_update`). That is a separate bottleneck documented in the bottleneck reports.

---

## 6. Source reports & raw data

| Report | Load balancer | Focus |
|--------|---------------|-------|
| [`BOTTLENECK_REPORT_CUSTOM_LB.md`](../stress/BOTTLENECK_REPORT_CUSTOM_LB.md) | Custom `:8088` | Full before/after (service + concurrent + serial) |
| [`BOTTLENECK_REPORT_ROUND_ROBIN.md`](../stress/BOTTLENECK_REPORT_ROUND_ROBIN.md) | Round-robin `:8090` | Full before/after (service + concurrent + serial) |
| [`BOTTLENECK_REPORT.md`](../stress/BOTTLENECK_REPORT.md) | Custom `:8088` | Early baseline (serial-only, **20.3%** median) |
| [`results/bottleneck_summary_custom_lb.json`](../stress/results/bottleneck_summary_custom_lb.json) | Custom | Machine-readable |
| [`results/bottleneck_summary_rr.json`](../stress/results/bottleneck_summary_rr.json) | Round-robin | Machine-readable |

### Re-run benchmarks

```bash
# Custom LB
python scripts/benchmark_bottleneck.py --lb custom -n 200 --concurrency 25 --concurrent-requests 500

# Round-robin
python scripts/benchmark_bottleneck.py --lb round_robin -n 200 --concurrency 25 --concurrent-requests 500
```

---

## 7. Implementation references

| Component | Path |
|-----------|------|
| Cache-aside | `app/product/catalog_cache.py` |
| Bypass header (benchmark only) | `app/product/views.py` |
| AOP-style timing | `app/common/performance_monitor.py` |
| Stats API | `GET /api/performance/stats/` |
| Benchmark runner | `scripts/benchmark_bottleneck.py` |
| LB comparison doc | [`LOAD_BALANCING_ROUND_ROBIN_VS_CUSTOM.md`](LOAD_BALANCING_ROUND_ROBIN_VS_CUSTOM.md) |
| Custom LB design | [`CUSTOM_LOAD_BALANCING.md`](CUSTOM_LOAD_BALANCING.md) |
