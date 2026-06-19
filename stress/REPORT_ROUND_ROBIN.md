# Stress Test Report — Django + Round-Robin (Requirement #9)

**Generated:** 2026-06-19 12:30 UTC  
**Framework:** Django + DRF + PostgreSQL + Redis + Gunicorn (3 replicas)  
**Load balancer:** Round-robin baseline (`openresty-rr` on **http://localhost:8090**)  
**Result:** **PASS**

---

## 1. Objective

Demonstrate that the Django e-commerce API remains **stable under 100 concurrent virtual users** when traffic is distributed with **plain round-robin** across:

- `app_main` (SMALL tier)
- `app_worker_1` (MEDIUM tier)
- `app_worker_2` (MONSTER tier)

---

## 2. Architecture under test

```
Locust (100 users)
       │
       ▼
openresty-rr :8090  ── round-robin ──┬── app_main
                                      ├── app_worker_1
                                      └── app_worker_2
                                              │
                                              ▼
                                    PostgreSQL + Redis
```

Round-robin sends ~**33%** of requests to each replica. No affinity, no live-state routing.

---

## 3. Test configuration

| Parameter | Value |
|-----------|-------|
| Entry point | `http://localhost:8090` |
| Load balancer | **Round-robin** (`openresty-rr`) |
| Concurrent users | **100** |
| Spawn rate | 10 users/s |
| Duration | 120 seconds |
| Tool | Locust 2.44 (headless) |
| Profile | `stress/locustfile_stress.py` |
| Pre-run seed | Product stock → 5000 units each |
| Wallet seed | $1000 per virtual user (on signup) |

### Workload mix

| Task | Weight | Endpoint |
|------|-------:|----------|
| Health check | 2 | `GET /api/health/` |
| Product list | 5 | `GET /api/products/` |
| Product detail | 3 | `GET /api/products/{id}/` |
| Add to cart | 4 | `POST /api/cart/create/` |
| Checkout | 3 | `POST /api/invoices/create/` |
| Wallet view | 1 | `GET /api/wallets/my-wallet/` |

Each virtual user signs up and logs in once at start.

---

## 4. Results

| Metric | Value |
|--------|------:|
| **Total HTTP requests** | **2,158** |
| **Throughput** | **17.88 req/s** |
| **Median latency** | **1,600 ms** |
| **p95 latency** | **28,000 ms** |
| **Locust failures (all)** | **0 (0.0%)** |
| **Checkout attempts** | **179** |
| **Checkout conflicts (409)** | **0** |
| **HTTP 5xx errors** | **0** |

### Per-endpoint highlights

| Endpoint | Requests | Median | p95 | Failures |
|----------|----------|-------:|----:|---------:|
| Signup User | 100 | 30,000 ms | 48,000 ms | 0 |
| Login User | 100 | 28,000 ms | 46,000 ms | 0 |
| Get Product List | 576 | 1,500 ms | 8,500 ms | 0 |
| Create Order Invoice | 179 | 1,900 ms | 7,500 ms | 0 |
| Health Check | 128 | 1,300 ms | 4,500 ms | 0 |
| Add to Cart | 269 | 1,500 ms | 8,500 ms | 0 |

Signup/login dominate tail latency (bcrypt password hashing at user spawn). Business API paths (products, cart, checkout) stayed in the **1.5–2.5 s median** range under 100 users.

### Data integrity (post-run)

| Check | Result |
|-------|--------|
| Negative product stock rows | **0** |
| Negative wallet balance rows | **0** |
| Integrity pass | **YES** |

---

## 5. Interpretation

### Stability

The system handled **100 concurrent users for 120 seconds** with:

- **Zero HTTP failures** reported by Locust (including no 5xx)
- **Zero data corruption** in PostgreSQL after the run
- **179 successful checkouts** with pessimistic locking intact

### Latency profile

- **Aggregated p95 (28 s)** is inflated by one-time **signup/login** cost per user (~100 bcrypt operations during ramp-up).
- **Checkout median (1.9 s)** and **product list median (1.5 s)** reflect steady-state API behavior under round-robin load.
- No server crash, no connection refused, no cascade failures.

### Round-robin distribution

Traffic was spread across all three Gunicorn replicas via nginx upstream rotation. Response header `X-Served-By` confirms replica attribution on each request.

---

## 6. Conclusion

**PASS** — The Django e-commerce stack with **round-robin load balancing** sustained **100 concurrent users** for **120 seconds** with:

- **2,158 total requests** at **17.9 req/s**
- **0 HTTP 5xx errors**
- **0 Locust failures**
- **0 negative stock / wallet rows**

The system meets requirement **#9** for stress stability: no collapse and no data loss under 100+ concurrent users.

---

## 7. Artifacts

- `stress/results/stress_run_rr_stats.csv`
- `stress/results/stress_run_rr.html`
- `stress/results/stress_summary_rr.json`

## 8. Reproduce

```bash
docker compose -f docker-compose.prod.yml up -d
python scripts/run_stress_test.py --lb round_robin -u 100 -r 10 -t 120
```
