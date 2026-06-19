# Stress testing & bottleneck analysis (Requirements #9 & #10)

**Report index:** [`index.md`](index.md) — all stress/benchmark reports and what each one covers.  
**Redis before/after (both LBs):** [`docs/REDIS_CACHE_BEFORE_AFTER.md`](../docs/REDIS_CACHE_BEFORE_AFTER.md)

Django equivalents of the Spring Boot stress stack (`stress/e-commerce-load-test.jmx`, `stress/locustfile.py`, `PerformanceMonitorAspect`).

## Requirement #9 — Stress testing (100+ concurrent users)

### Quick run

```bash
docker compose -f docker-compose.prod.yml up -d
python scripts/run_stress_test.py -u 100 -r 10 -t 120
```

### What it does

1. Waits for `GET /api/health/`
2. Seeds product stock to **5000** units
3. Runs **Locust** headless (`stress/locustfile_stress.py`) with 100+ virtual users
4. Checks PostgreSQL integrity (no negative stock / wallets)
5. Writes:
   - `stress/REPORT.md`
   - `stress/results/stress_summary.json`
   - `stress/results/stress_run_stats.csv` + HTML report

### Locust UI (manual)

```bash
docker compose -f docker-compose.prod.yml up locust
# Open http://localhost:8089 — use locustfile_stress.py or e_commerce/locustfile.py
```

### Pass criteria

| Check | Expected |
|-------|----------|
| Concurrent users | ≥ 100 |
| HTTP 5xx | 0 |
| Negative stock rows | 0 |
| Negative wallet rows | 0 |
| Checkout 409 | Allowed (locking conflicts under load) |

---

## Requirement #10 — Benchmarking & bottleneck analysis

### Quick run

```bash
python scripts/benchmark_bottleneck.py --host http://localhost:8088 -n 200
```

### What it measures

| Phase | Description |
|-------|-------------|
| **Service-layer** | `@monitor_execution` on `get_product_cached` — reset stats between concurrent phases |
| **Concurrent HTTP** | 25 workers × 500 requests — cache vs DB under parallel load |
| **Serial HTTP** | Single client (reference; LB overhead often dominates) |
| **BEFORE** | Product detail with `X-Bypass-Product-Cache: 1` — PostgreSQL every request |
| **AFTER** | Normal Redis cache-aside (`get_product_cached`) |

### Monitoring (AOP equivalent)

| Spring | Django |
|--------|--------|
| `PerformanceMonitorAspect` `@Around` on `core.service.*` | `@monitor_execution` on service functions |
| SLF4J logs | `performance` logger + `GET /api/performance/stats/` |
| — | `PerformanceMonitorMiddleware` on `/api/*` |

Monitored service paths:

- `product.get_product_cached`
- `invoices.checkout`
- `product.adjust_stock`

### Outputs

- `stress/BOTTLENECK_REPORT.md` — baseline before/after (preserved)
- `stress/BOTTLENECK_REPORT_CUSTOM_LB.md` — cache benchmark via custom LB (`:8088`)
- `stress/BOTTLENECK_REPORT_ROUND_ROBIN.md` — cache benchmark via round-robin (`:8090`)
- `stress/index.md` — master index of all reports
- `docs/REDIS_CACHE_BEFORE_AFTER.md` — Redis impact comparison (both LBs)
- `stress/results/bottleneck_summary.json` — baseline JSON summary
- `stress/results/bottleneck_summary_custom_lb.json` — custom LB JSON summary

```bash
# Baseline (writes BOTTLENECK_REPORT.md)
python scripts/benchmark_bottleneck.py --host http://localhost:8088 -n 300

# Custom LB (separate report; does not overwrite baseline)
python scripts/benchmark_bottleneck.py --lb custom -n 200 --concurrency 25 --concurrent-requests 500

# Round-robin
python scripts/benchmark_bottleneck.py --lb round_robin -n 200 --concurrency 25 --concurrent-requests 500
```

---

## Entry points

| URL | Purpose |
|-----|---------|
| `http://localhost:8088` | Custom load balancer (recommended for stress) |
| `http://localhost:8090` | Round-robin baseline |
| `GET /api/health/` | Liveness probe |
| `GET /api/performance/stats/` | Aggregated timings |
| `DELETE /api/performance/stats/` | Reset counters before benchmark |

---

## Related docs

| Document | Content |
|----------|---------|
| [index.md](index.md) | Master index of all stress/benchmark reports |
| [REDIS_CACHE_BEFORE_AFTER.md](../docs/REDIS_CACHE_BEFORE_AFTER.md) | Redis cache before/after on custom LB and round-robin |
| [CUSTOM_LOAD_BALANCING.md](../docs/CUSTOM_LOAD_BALANCING.md) | Architecture, abstract, examples, when custom LB shines |
| [LOAD_BALANCING_ROUND_ROBIN_VS_CUSTOM.md](../docs/LOAD_BALANCING_ROUND_ROBIN_VS_CUSTOM.md) | Full A/B comparison methodology |
| [REPORT_CUSTOM_LB.md](REPORT_CUSTOM_LB.md) | 100-user custom LB stress report |
| [REPORT_ROUND_ROBIN.md](REPORT_ROUND_ROBIN.md) | 100-user round-robin stress report |
