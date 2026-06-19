# Stress Test Report — Django + Custom Load Balancer (Requirement #9)

**Generated:** 2026-06-19 12:36 UTC  
**Framework:** Django + DRF + PostgreSQL + Redis + Gunicorn (3 replicas)  
**Load balancer:** Custom OpenResty LB (`openresty` on **http://localhost:8088**)  
**Result:** **PASS**

---

## 1. Objective

Demonstrate **100 concurrent users** through the **custom load balancer** without server collapse or data corruption.

---

## 2. Architecture under test

```
Locust (100 users)
       │
       ▼
openresty :8088  ── affinity + P2C + live Redis state ──┬── app_main (SMALL)
                                                         ├── app_worker_1 (MEDIUM)
                                                         └── app_worker_2 (MONSTER)
                                                                  │
                                                                  ▼
                                                        PostgreSQL + Redis
                                                        decision-cache (atlas)
```

Unlike round-robin (`:8090`), the custom LB classifies requests by **compute units**, reads **live node load** from Redis, and routes via **Power-of-Two Choices** with **tier affinity**.

---

## 3. Test configuration

| Parameter | Value |
|-----------|-------|
| Entry point | `http://localhost:8088` |
| Load balancer | **Custom** (OpenResty + Lua + decision-cache) |
| Concurrent users | **100** |
| Spawn rate | 10 users/s |
| Duration | 120 seconds |
| Tool | Locust 2.44 (headless) |
| Profile | `stress/locustfile_stress.py` |
| Pre-run seed | Product stock → 5000 |

---

## 4. Results

| Metric | Custom LB | Round-robin (same test)* |
|--------|----------:|-------------------------:|
| **Total requests** | **3,561** | 2,158 |
| **Throughput** | **28.9 req/s** | 17.9 req/s |
| **Median latency** | **750 ms** | 1,600 ms |
| **p95 latency** | 14,000 ms | 28,000 ms |
| **Checkout attempts** | **332** | 179 |
| **Locust failures** | **0** | 0 |
| **HTTP 5xx** | **0** | 0 |

\*Round-robin numbers from `stress/REPORT_ROUND_ROBIN.md` (same 100 users / 120 s profile).

### Data integrity (post-run)

| Check | Result |
|-------|--------|
| Negative product stock | **0** |
| Negative wallet balance | **0** |
| Integrity pass | **YES** |

---

## 5. Why custom LB performed better here

Under mixed e-commerce traffic (reads + cart + checkout):

1. **Compute-aware routing** — checkout (900 units) steered toward MONSTER tier (`app_worker_2`).
2. **Live load scoring** — P2C avoided replicas with high active request counts.
3. **Tier affinity** — light reads did not unnecessarily overload the SMALL node.

Round-robin sent equal share to all three replicas regardless of tier or load.

---

## 6. Conclusion

**PASS** — 100 concurrent users for 120 s through **custom load balancing** with:

- **3,561 requests** at **28.9 req/s**
- **0 HTTP 5xx**, **0 Locust failures**
- **0 negative stock / wallet rows**
- **62% higher throughput** vs round-robin in the paired comparison

Full design documentation: [`docs/CUSTOM_LOAD_BALANCING.md`](../docs/CUSTOM_LOAD_BALANCING.md)

---

## 7. Artifacts

- `stress/results/stress_run_custom_stats.csv`
- `stress/results/stress_run_custom.html`
- `stress/results/stress_summary_custom.json`

## 8. Re-run

```bash
docker compose -f docker-compose.prod.yml up -d
python scripts/run_stress_test.py --lb custom -u 100 -r 10 -t 120
```
