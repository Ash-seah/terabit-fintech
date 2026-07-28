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
- WebSocket tester (browser): <http://localhost:8000/api/ws-tester>
- WebSocket AsyncAPI docs: <http://127.0.0.1:8080>
- Readiness: <http://localhost:8000/health/ready>

### Production Nginx note

If the host proxies only `location /api` and `location /ws` (as on
`fintech.terabitventure.com`), use:

- Swagger: `https://fintech.terabitventure.com/api/docs`
- ReDoc: `https://fintech.terabitventure.com/api/redoc`
- WebSocket tester: `https://fintech.terabitventure.com/api/ws-tester`
- Live WebSocket: `wss://fintech.terabitventure.com/ws/live`
- Symbols: `https://fintech.terabitventure.com/api/v1/symbols?asset_class=stocks`
- TradingView OHLC: `https://fintech.terabitventure.com/api/v1/charts/AAPL`

Do not bind AsyncAPI `:8080` to `0.0.0.0` on a public VPS; scanners will hit it.
Keep it on `127.0.0.1` and optionally proxy it through Nginx.

The checked-in `.env.example` is safe to copy. `.env` is ignored and contains local
Compose values. Rotate any API key that has been pasted into chat or logs before
deploying.

## REST endpoints

- `GET /api/v1/symbols?asset_class=stocks|crypto|forex` — name, description, price, day change
  - omit `asset_class` to include all three categories (`asset_class=all`)
  - `sorted_by=symbol|name|price|change|change_percent|volatility`
  - `order=asc|desc` (defaults to `desc` for price/change/volatility)
  - `page` + `limit` pagination (e.g. top 10 movers:
    `?asset_class=crypto&sorted_by=volatility&limit=10`)
- `GET /api/v1/marketmap` — US stocks heatmap tiles grouped by sector
  - response `sectors[]` ordered by importance then population (Technology, Financials, …)
  - each sector has its own sorted `items[]` (name, logo, blurb, market cap, day change)
  - `sorted_by=change_percent` (default), also `change|volatility|market_cap|price|name|symbol`
  - optional `limit` caps items **per sector**
- `GET /api/v1/charts/{ticker}?interval=1d` — TradingView Lightweight Charts OHLC
- `GET /api/v1/historical/{ticker}?interval=1d` — same bars as structured points (defaults to deepest available history)
- `GET /api/v1/quotes/{symbol}`
- `GET /api/v1/symbols/search?q=Apple`
- `GET /api/v1/market/status` — US market (no exchange picker)
- `GET /api/v1/companies/{symbol}/profile`
- `GET /api/v1/companies/{symbol}/news`
- `GET /api/v1/companies/{symbol}/peers`
- `GET /api/v1/companies/{symbol}/fundamentals`
- `GET /api/v1/companies/{symbol}/earnings`
- `GET /api/v1/companies/{symbol}/recommendations`
- `GET /api/v1/calendars/earnings` — defaults to the next 30 days

Use `asset_class=stocks` for equities (e.g. `NVDA`), `crypto` for coins (e.g. `BTC-USD`), and `forex` for FX pairs (e.g. `EUR-USD`).
Prices refresh in the background; the first response after deploy may have null prices for a few seconds.

Market payloads are returned unwrapped (no provider/resource envelope). Entitlement
failures are `403`; quota exhaustion `429`; upstream outages `503`.

Quota strategy: symbols and quotes use Yahoo + live WebSocket cache first. Finnhub
REST is reserved for fundamentals/news/calendars/search, soft-cached aggressively
(stale responses are served while refreshing), and capped at
`FINNHUB_REST_CALLS_PER_MINUTE` (default 20).

Historical requests check Redis, then sufficiently fresh PostgreSQL bars, and finally
run the synchronous yfinance request in a worker thread. New bars are upserted into
PostgreSQL and cached for 15 minutes. Daily charts default to `max` history.

## WebSocket

Open the interactive tester at `/api/ws-tester` (works behind your Nginx `/api` proxy).

Connect to all configured symbols:

```text
ws://localhost:8000/ws/live
```

Or select a configured subset:

```text
ws://localhost:8000/ws/live?symbols=AAPL,NVDA,BTC-USD
```

The server sends `trade` batches and a heartbeat after 30 seconds without client
traffic. Slow clients have bounded queues and are disconnected instead of delaying
the broadcast loop. The curated live-stream universe is always subscribed on the
upstream Finnhub socket. `STREAM_SYMBOLS` is only for optional extras.

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
