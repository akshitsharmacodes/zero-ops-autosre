# victim-service

Small analytics API used as AutoSRE's demo target.

| Endpoint | Description |
|---|---|
| `GET /api/health/` | Liveness |
| `GET /api/reports/top-pages/` | Most viewed pages (raw SQL via the reporting pool) |
| `GET /api/metrics/summary/` | Totals via the ORM |
| `GET /api/reports/user-activity/` | Per-user activity (raw SQL via the reporting pool) |

Run tests: `python -m pytest`

Load test: `python traffic_simulator.py --base-url http://localhost:8001`
