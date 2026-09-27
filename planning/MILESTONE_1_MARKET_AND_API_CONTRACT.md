# Milestone 1 — Market-data reconciliation and API contract

**Status:** accepted for implementation

## Authority and scope

The active project specification is `PLAN.md` §§6–9 and Appendix A, plus
`MARKET_DATA_SUMMARY.md`. The five documents formerly in `planning/archive/`
are historical only. In particular, do not implement correlated simulation,
shock events, portfolio snapshots, or `/api/portfolio/history` from those
documents.

This checkout was missing its `planning/` directory. The documents used for
this decision are the matching project planning files in the adjacent
`simulated_trading_agent_team_8` workspace. This file is the local,
implementation-facing source of truth until those project documents are
restored here.

This milestone deliberately changes neither `frontend/` nor any test file.

## ADR: one market subsystem, adapted to this application layout

### Context

The planning summary describes a completed `backend/market/` package with a
provider, poller, cache, and stream hub. This checkout instead has a legacy
`backend/app/market/` implementation: it owns a process-global cache, starts
fixed tickers, writes from providers directly, uses correlated/shock
simulation, and streams directly from the cache.

The latter conflicts with the active behavioral contract, but importing both
layouts would create competing providers and caches in one FastAPI process.

### Decision

Keep `backend/app/market/` as the physical package because this application is
already structured around `app.*` imports. Replace its legacy internals with
the documented market subsystem's public semantics. There must be exactly one
market service bundle and one injected `PriceCache`; module-global market
state is retired.

The canonical flow is:

```
MarketDataProvider -> MarketPoller -> PriceCache -> PriceStreamHub -> SSE
```

- Providers are pull-only: `get_prices(tickers)` and `validate_ticker(ticker)`.
- `MarketPoller` is the sole provider caller and writes to the cache.
- `PriceStreamHub` broadcasts at 500 ms through per-client queues; it computes
  direction against the last *emitted*, rounded value and re-emits unchanged
  prices as `flat`.
- The app owns a synchronous ticker registry populated from `watchlist U
  positions` at startup and maintained after successful watchlist, trade, and
  reset actions. This avoids performing async SQLite work in the poller's
  synchronous ticker supplier.
- FastAPI lifespan order is: initialize DB; initialize ticker registry;
  construct provider/cache/poller/hub; start poller then hub. Shutdown is hub
  then poller/provider.
- The SSE route subscribes to the hub and always unsubscribes in `finally`.
- Portfolio valuation, trading, health, and the SSE route consume the injected
  cache. No request route calls a provider directly.

## Cross-cutting API rules

- Symbols are normalized with `ticker.upper().strip()`.
- Persisted IDs are UUID strings.
- All timestamps are UTC ISO-8601 strings ending in `Z`.
- Application-domain failures return:

  ```json
  {"error":{"code":"machine_code","message":"Human-readable explanation"}}
  ```

  Use 400 for domain validation/business failures, 404 for absent resources,
  and 503 for an unavailable configured dependency or stale market feed.
  Framework 422 responses are reserved for malformed JSON or type errors.
- Prices, cash, P&L, and total values are rounded to two decimals. Fractional
  quantities are supported and must be at least `0.0001`.

## API contract

### Market stream

`GET /api/stream/prices` returns `200 text/event-stream`. Every approximately
500 ms, publish one named `price` event for each known ticker, including
unchanged prices:

```text
event: price
data: {"ticker":"AAPL","price":190.12,"previous_price":189.98,"timestamp":"2026-09-26T12:00:00.000Z","direction":"up"}

```

`direction` is `up`, `down`, or `flat`; `previous_price` is the previously
emitted price. Known tickers are all watched symbols plus held symbols, so
removing a held symbol from the watchlist does not stop valuation or streaming.

### Portfolio

`GET /api/portfolio` returns:

```json
{
  "cash_balance": 10000.0,
  "total_value": 10000.0,
  "positions": [
    {
      "ticker": "AAPL",
      "quantity": 10,
      "avg_cost": 190.12,
      "current_price": 191.0,
      "unrealized_pnl": 8.8,
      "pnl_percent": 0.46
    }
  ]
}
```

Current prices come from the canonical cache, falling back to average cost
only before a first market price arrives.

`POST /api/portfolio/trade` accepts:

```json
{"ticker":"AAPL","quantity":10,"side":"buy"}
```

`side` is `buy` or `sell`. Success is `200`:

```json
{
  "trade":{"id":"uuid","ticker":"AAPL","side":"buy","quantity":10,"price":190.12,"executed_at":"2026-09-26T12:00:00.000Z"},
  "cash_balance":8098.8,
  "position":{"ticker":"AAPL","quantity":10,"avg_cost":190.12}
}
```

`position` is `null` when a sale closes it. One shared transactional service
must validate and execute both manual and chat trades, update cash/positions,
append the trade audit record, and delete effectively-zero positions using an
epsilon. Valid 400 error codes are `invalid_quantity`, `unknown_ticker`,
`insufficient_cash`, and `insufficient_shares`.

`GET /api/portfolio/trades` returns a JSON array, newest first, of trade
objects from the `trade` field above.

`POST /api/portfolio/reset` atomically restores $10,000 cash and the exact ten
default tickers, and deletes positions, trades, and chat messages without
deleting the database volume. It returns:

```json
{"ok":true,"portfolio":{},"watchlist":[]}
```

where `portfolio` and `watchlist` have their normal response shapes.

### Watchlist

`GET /api/watchlist` returns items ordered by `added_at`; prices belong solely
to the SSE stream:

```json
[{"ticker":"AAPL","added_at":"2026-09-26T12:00:00.000Z"}]
```

`POST /api/watchlist` accepts `{"ticker":"PYPL"}`. A new entry and a
duplicate both return `200` with the item; a duplicate preserves its original
`added_at`. New symbols are validated by the provider and added to the ticker
registry. An unknown ticker returns 400 `unknown_ticker`; a new symbol beyond
30 entries returns 400 `watchlist_full`.

`DELETE /api/watchlist/{ticker}` returns `{"ok":true}` or 404 `not_found`.
Removing a held ticker only removes watchlist membership.

### Chat

`POST /api/chat` accepts `{"message":"buy 10 AAPL"}`. Empty messages return
400 `invalid_message`. With `LLM_MOCK=true`, deterministic model output still
runs through the same action services. With mock disabled and no configured
`OPENROUTER_API_KEY`, it returns 503 `llm_not_configured`.

Successful responses always include stable action arrays and a post-action
portfolio snapshot:

```json
{
  "message":"Buying AAPL.",
  "actions":{
    "trades":[{"ticker":"AAPL","side":"buy","quantity":10,"status":"filled","price":190.12,"error":null}],
    "watchlist_changes":[{"ticker":"PYPL","action":"add","status":"applied","error":null}]
  },
  "portfolio":{}
}
```

Trade statuses are `filled` or `rejected`; watchlist statuses are `applied`,
`noop`, or `rejected`. An individual rejected action is represented in its
result rather than changing the whole request to an HTTP failure. Persist the
user message followed by the assistant response including action outcomes;
never alter assistant prose to append error text.

`GET /api/chat/history` returns at most 20 records, oldest first:

```json
[{"id":"uuid","role":"assistant","content":"...","actions":{},"created_at":"2026-09-26T12:00:00.000Z"}]
```

`actions` is `null` for user records.

### Health

`GET /api/health` returns:

```json
{"status":"ok","db":"ok","market_feed":{"source":"simulator","last_update_age_ms":320}}
```

It probes the database and cache freshness. Database failure, an empty cache,
or an update older than 10 seconds returns 503 with `status: "degraded"` and
the same diagnostic fields.

## Backend implementation sequence

1. Port/adapt the canonical provider, poller, cache, hub, simulator, Massive
   client, and factory semantics into `app.market`; remove all legacy global
   cache/provider paths once imports are migrated.
2. Add the app-state market service bundle and ticker registry, then wire SSE
   and health to it.
3. Move the database to `/app/db/simulated_trading.db`, use UTC `Z` timestamps,
   and remove `portfolio_snapshots`, the recorder, and the history endpoint.
4. Introduce shared portfolio read-model, trade transaction, and watchlist
   action services. Route and chat code must call these services rather than
   duplicate SQL/business rules.
5. Add the portfolio blotter/reset and chat-history routes, then update the
   Docker bind mount and healthcheck.
6. Only after those backend contracts are implemented may frontend and test
   work begin.

## Milestone-1 acceptance criteria

- No runtime code imports or instantiates a legacy global market cache/provider.
- One app-state service bundle controls market lifecycle.
- The documented SSE and REST response shapes above are the only contract for
  future frontend and test changes.
- Legacy snapshot/history, correlated simulation, and shock-event behavior are
  explicitly non-goals.
