# Round-robin stress test — 100 users (Requirement #9)

Generate the report against **openresty-rr** on port **8090** (plain nginx round-robin across 3 Django replicas).

## Prerequisites

1. **Docker Desktop** running
2. Stack up:

```bash
cd django_ecomerce
docker compose -f docker-compose.prod.yml up -d --build
```

3. Wait until health checks pass:

```bash
curl http://localhost:8090/api/health/
```

## Run (100 concurrent users, 120 seconds)

```bash
python scripts/run_stress_test.py --lb round_robin -u 100 -r 10 -t 120
```

This will:

- Seed product stock to **5000**
- Run Locust (`stress/locustfile_stress.py`) through **round-robin** (`http://openresty-rr:80` inside Docker)
- Verify DB integrity (no negative stock / wallets)
- Write **`stress/REPORT_ROUND_ROBIN.md`**

## Outputs

| File | Description |
|------|-------------|
| `stress/REPORT_ROUND_ROBIN.md` | Submission report |
| `stress/results/stress_run_rr_stats.csv` | Locust metrics |
| `stress/results/stress_run_rr.html` | Locust HTML dashboard |
| `stress/results/stress_summary_rr.json` | Machine-readable summary |

## Pass criteria

| Check | Expected |
|-------|----------|
| Concurrent users | 100 |
| Load balancer | Round-robin `:8090` |
| HTTP 5xx | 0 |
| Negative stock | 0 |
| Negative wallets | 0 |
| Checkout 409 | OK under lock contention |

## Manual Locust UI

Point Locust at round-robin:

```bash
docker compose -f docker-compose.prod.yml exec locust \
  locust -f ./stress/locustfile_stress.py --host=http://openresty-rr:80
```

Open http://localhost:8089 and start **100 users**.
