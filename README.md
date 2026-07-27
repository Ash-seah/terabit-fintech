# Financial Data Backend

FastAPI service that combines yfinance historical/EOD data with Finnhub REST and
real-time trades. PostgreSQL is the durable source for fetched history and live
aggregates; Redis provides response caching, quota protection, locks, latest prices,
and WebSocket fan-out.

## Run

Requirements: Docker Desktop with Compose.

```bash
docker compose up --build
```

The API waits for PostgreSQL and Redis, applies Alembic migrations, then starts one
Uvicorn worker. One worker is intentional: a process starts one Finnhub WebSocket and
the free plan permits a limited number of upstream subscriptions.

- REST API: <http://localhost:8000>
- Swagger UI: <http://localhost:8000/api/docs>
- ReDoc: <http://localhost:8000/api/redoc>
- OpenAPI JSON: <http://localhost:8000/api/openapi.json>
- WebSocket AsyncAPI docs: <http://127.0.0.1:8080>
- Readiness: <http://localhost:8000/health/ready>

### Production Nginx note

If the host proxies only `location /api` and `location /ws` (as on
`fintech.terabitventure.com`), use:

- Swagger: `https://fintech.terabitventure.com/api/docs`
- ReDoc: `https://fintech.terabitventure.com/api/redoc`
- Live WebSocket: `wss://fintech.terabitventure.com/ws/live`
- Example REST: `https://fintech.terabitventure.com/api/v1/quotes/AAPL`

Do not bind AsyncAPI `:8080` to `0.0.0.0` on a public VPS; scanners will hit it.
Keep it on `127.0.0.1` and optionally proxy it through Nginx.

The checked-in `.env.example` is safe to copy. `.env` is ignored and contains local
Compose values. Rotate any API key that has been pasted into chat or logs before
deploying.

## REST endpoints

- `GET /api/v1/historical/{ticker}?period=1mo&interval=1d`
- `GET /api/v1/quotes/{symbol}`
- `GET /api/v1/symbols/search?q=Apple`
- `GET /api/v1/symbols/stocks/{exchange}`
- `GET /api/v1/market/status/{exchange}`
- `GET /api/v1/companies/{symbol}/profile`
- `GET /api/v1/companies/{symbol}/news?from_date=2026-07-01&to_date=2026-07-27`
- `GET /api/v1/companies/{symbol}/peers`
- `GET /api/v1/companies/{symbol}/fundamentals`
- `GET /api/v1/companies/{symbol}/earnings`
- `GET /api/v1/companies/{symbol}/recommendations`
- `GET /api/v1/calendars/earnings?from_date=2026-07-01&to_date=2026-07-31`
- `GET /api/v1/forex/exchanges`
- `GET /api/v1/forex/symbols/{exchange}`
- `GET /api/v1/crypto/exchanges`
- `GET /api/v1/crypto/symbols/{exchange}`

Every Finnhub response says whether it came from cache or stale PostgreSQL fallback.
Provider entitlement failures are returned as `403`; local/upstream quota exhaustion
as `429`; provider outages as `503`.

Historical requests check Redis, then sufficiently fresh PostgreSQL bars, and finally
run the synchronous yfinance request in a worker thread. New bars are upserted into
PostgreSQL and cached for 15 minutes.

## WebSocket

Connect to all configured symbols:

```text
ws://localhost:8000/ws/live
```

Or select a configured subset:

```text
ws://localhost:8000/ws/live?symbols=AAPL,BINANCE:BTCUSDT
```

The server sends `trade` batches and a heartbeat after 30 seconds without client
traffic. Slow clients have bounded queues and are disconnected instead of delaying
the broadcast loop. Configure up to the provider allowance with `STREAM_SYMBOLS`.

## Storage and caching

- Historical OHLCV and one-minute live aggregates are retained permanently.
- Raw trades are batched into PostgreSQL and deleted after
  `RAW_TRADE_RETENTION_DAYS` (30 by default).
- Profiles, news, fundamentals, calendars, and other REST snapshots are durable JSON
  fallback records.
- Redis TTLs vary by volatility: quotes 5 seconds, status 60 seconds, news 5 minutes,
  calendars/search one hour, fundamentals six hours, and reference lists/profiles
  one day.
- A Redis global token bucket defaults to 55 Finnhub REST requests per minute,
  below the published free ceiling of 60. Public clients default to 120 REST requests
  per IP per minute.

## Development checks

```bash
python -m pip install -e ".[dev]"
ruff check .
mypy app
pytest
```

## Provider constraints

Finnhub's published free plan currently advertises 60 REST calls/minute and 50
WebSocket symbols. Dataset entitlement varies; many endpoints shown in the public
documentation require paid access. This service never bypasses those restrictions
and exposes an explicit entitlement error. The free license is described as personal
use; verify Finnhub and Yahoo terms before redistributing or using this service
commercially. yfinance is an unofficial Yahoo Finance client and has no availability
SLA.

This API intentionally has no application authentication. Put it behind a trusted
gateway, firewall, or private network before exposing it to the internet.
