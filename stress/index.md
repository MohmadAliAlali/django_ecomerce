# Stress, Benchmark & Report Index

Central index for all **requirement #9 (stress testing)**, **requirement #10 (benchmarking / bottleneck analysis)**, and **load-balancing** reports in this project.

**Quick links**

| Topic | Document |
|-------|----------|
| Redis cache before/after (both LBs) | [`docs/REDIS_CACHE_BEFORE_AFTER.md`](../docs/REDIS_CACHE_BEFORE_AFTER.md) |
| Custom LB design | [`docs/CUSTOM_LOAD_BALANCING.md`](../docs/CUSTOM_LOAD_BALANCING.md) |
| Round-robin vs custom LB A/B | [`docs/LOAD_BALANCING_ROUND_ROBIN_VS_CUSTOM.md`](../docs/LOAD_BALANCING_ROUND_ROBIN_VS_CUSTOM.md) |
| How to run tests | [`stress/README.md`](README.md) |

---

## Requirement #9 — Stress testing (100+ concurrent users)

Proves the stack survives **100 virtual users** for 120 seconds without 5xx errors or data corruption.

| Report | Entry point | What it covers |
|--------|-------------|----------------|
| [**REPORT_CUSTOM_LB.md**](REPORT_CUSTOM_LB.md) | `http://localhost:8088` | **Custom OpenResty LB** — affinity, P2C, live Redis node state. **3,561** requests, **28.9 req/s**, 0 failures, integrity PASS. Compares headline numbers to round-robin. |
| [**REPORT_ROUND_ROBIN.md**](REPORT_ROUND_ROBIN.md) | `http://localhost:8090` | **Round-robin baseline** — plain nginx RR across 3 replicas. **2,158** requests, **17.9 req/s**, 0 failures, integrity PASS. Documents workload mix (health, catalog, cart, checkout, wallet). |
| [**RUN_ROUND_ROBIN.md**](RUN_ROUND_ROBIN.md) | — | **How-to** for generating the round-robin stress report (`run_stress_test.py --lb round_robin`). Not a results report. |

**Runner:** `python scripts/run_stress_test.py --lb custom|round_robin -u 100 -r 10 -t 120`

**Raw artifacts**

| File | Description |
|------|-------------|
| `results/stress_summary_custom.json` | Custom LB run metrics (JSON) |
| `results/stress_summary_rr.json` | Round-robin run metrics (JSON) |
| `results/stress_run_custom_stats.csv` | Locust per-endpoint stats (custom) |
| `results/stress_run_rr_stats.csv` | Locust per-endpoint stats (RR) |
| `results/stress_run_custom.html` | Locust HTML dashboard (custom) |
| `results/stress_run_rr.html` | Locust HTML dashboard (RR) |

**Locust profile:** [`locustfile_stress.py`](locustfile_stress.py)

---

## Requirement #10 — Benchmarking & bottleneck analysis

Identifies a **hot read path** (`GET /api/products/{id}/`), measures **before (no cache)** vs **after (Redis cache-aside)**, and documents numeric improvement.

| Report | Entry point | What it covers |
|--------|-------------|----------------|
| [**BOTTLENECK_REPORT_CUSTOM_LB.md**](BOTTLENECK_REPORT_CUSTOM_LB.md) | `:8088` custom LB | **Primary custom-LB cache report.** Service-layer **~64%** median gain; concurrent HTTP **~8%** median / **~5.5%** p95. Includes serial reference + `X-Served-By` routing. |
| [**BOTTLENECK_REPORT_ROUND_ROBIN.md**](BOTTLENECK_REPORT_ROUND_ROBIN.md) | `:8090` round-robin | **Same benchmark through RR.** Service-layer **~63%** median gain; concurrent HTTP **~11%** median / **~14%** p95. Shows even ~33% replica split during concurrent phase. |
| [**BOTTLENECK_REPORT.md**](BOTTLENECK_REPORT.md) | `:8088` | **Preserved early baseline** — serial-only measurement (**20.3%** median improvement). Kept for historical comparison; superseded by `BOTTLENECK_REPORT_*` pair for full methodology. |

**Cross-cutting analysis:** [`docs/REDIS_CACHE_BEFORE_AFTER.md`](../docs/REDIS_CACHE_BEFORE_AFTER.md) — side-by-side Redis impact for **both** load balancers.

**Runner:** `python scripts/benchmark_bottleneck.py --lb custom|round_robin -n 200 --concurrency 25 --concurrent-requests 500`

**Raw artifacts**

| File | Description |
|------|-------------|
| `results/bottleneck_summary_custom_lb.json` | Custom LB benchmark (JSON) |
| `results/bottleneck_summary_rr.json` | Round-robin benchmark (JSON) |
| `results/bottleneck_summary.json` | Early baseline benchmark (JSON) |

---

## Load balancing documentation (requirement #5 + comparisons)

| Document | What it covers |
|----------|----------------|
| [**docs/CUSTOM_LOAD_BALANCING.md**](../docs/CUSTOM_LOAD_BALANCING.md) | Architecture, abstract, compute units, P2C, affinity, decision-cache, when custom LB shines. Links to stress reports. |
| [**docs/LOAD_BALANCING_ROUND_ROBIN_VS_CUSTOM.md**](../docs/LOAD_BALANCING_ROUND_ROBIN_VS_CUSTOM.md) | Full A/B methodology: fair symmetric test, checkout-heavy degraded-node scenario, file map, honest “when RR wins / when custom wins” narrative. |
| [**docs/REDIS_CACHE_BEFORE_AFTER.md**](../docs/REDIS_CACHE_BEFORE_AFTER.md) | **Redis cache-aside before/after** on both `:8088` and `:8090` — service, concurrent, and serial views plus 100-user stress context. |

---

## Operational guide

| Document | What it covers |
|----------|----------------|
| [**README.md**](README.md) | Commands for stress + benchmark, monitoring (`@monitor_execution`, `/api/performance/stats/`), pass criteria. |
| [**RUN_ROUND_ROBIN.md**](RUN_ROUND_ROBIN.md) | Step-by-step round-robin stress only. |

---

## Entry points (Docker prod stack)

| URL | Role |
|-----|------|
| `http://localhost:8088` | Custom load balancer (recommended for stress) |
| `http://localhost:8090` | Round-robin baseline |
| `GET /api/health/` | Liveness probe |
| `GET /api/performance/stats/` | Aggregated service/request timings |
| `DELETE /api/performance/stats/` | Reset timing counters |

---

## Report map (by question)

| If you want to know… | Read |
|----------------------|------|
| Did 100 users break the system on **custom LB**? | [REPORT_CUSTOM_LB.md](REPORT_CUSTOM_LB.md) |
| Did 100 users break the system on **round-robin**? | [REPORT_ROUND_ROBIN.md](REPORT_ROUND_ROBIN.md) |
| How much did **Redis cache** help on **custom LB**? | [BOTTLENECK_REPORT_CUSTOM_LB.md](BOTTLENECK_REPORT_CUSTOM_LB.md) + [REDIS doc](../docs/REDIS_CACHE_BEFORE_AFTER.md) |
| How much did **Redis cache** help on **round-robin**? | [BOTTLENECK_REPORT_ROUND_ROBIN.md](BOTTLENECK_REPORT_ROUND_ROBIN.md) + [REDIS doc](../docs/REDIS_CACHE_BEFORE_AFTER.md) |
| Custom vs RR on throughput / latency / checkout? | [LOAD_BALANCING doc](../docs/LOAD_BALANCING_ROUND_ROBIN_VS_CUSTOM.md) + stress report comparison tables |
| How does the **custom LB** work internally? | [CUSTOM_LOAD_BALANCING.md](../docs/CUSTOM_LOAD_BALANCING.md) |
| How do I **re-run** everything? | [README.md](README.md) |
