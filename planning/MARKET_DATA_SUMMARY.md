# Market Data Backend — Summary

> Regenerated against the actual code in `backend/market/` and verified by running the real test suite (`uv run pytest tests/market/ -v`, from `backend/`). The previous version of this file described a different, nonexistent implementation (`backend/app/market/`, a `massive_client.py` using a `massive` package, Cholesky-correlated GBM, a Rich terminal demo, coverage numbers) — none of that matches what's on disk. This version reflects only what was directly read or executed.

**Status:** Market-data package builds and its own test suite passes (97/97). REST routes, the database layer, and LLM chat integration are **not** part of this package — per `backend/README.md` they're tracked separately and don't exist yet anywhere in the repo.

## What Was Built

A market-data subsystem in `backend/market/` (8 files, 683 lines total) providing a provider-agnostic interface, a GBM simulator, a Massive/Polygon.io REST client, a process-global price cache, and an in-process SSE fan-out hub.

### Architecture

```
MarketDataProvider (ABC, base.py)
├── SimulatedProvider (simulator.py)  →  independent per-ticker GBM (default, no key needed)
└── MassiveProvider (massive.py)      →  Massive/Polygon.io REST polling (when MASSIVE_API_KEY set)
        │
        ▼  (driven only by MarketPoller — nothing else calls the provider)
   MarketPoller (poller.py)
        │  writes ticks in
        ▼
   PriceCache (cache.py) — plain dict + threading.Lock, sync, process-global
        │  read on a fixed 500ms cadence
        ▼
   PriceStreamHub (hub.py) — computes direction, fans out to subscriber asyncio.Queues
        │
        ▼
   (no consumer yet — no FastAPI SSE route exists in the repo)
```

**Important scope gap:** `hub.py` implements `subscribe()`/`unsubscribe()`/fan-out over `asyncio.Queue`, matching the shape `GET /api/stream/prices` (PLAN §6) will need, but there is no FastAPI app, router, or endpoint anywhere in the repo yet — `backend/` contains only `market/`, `tests/`, `pyproject.toml`, and `README.md`. The hub is wired to nothing. Whoever builds the SSE endpoint still needs to write the `EventSource`-facing route.

### Modules

| File | Lines | Purpose |
|------|------:|---------|
| `__init__.py` | 18 | Re-exports the public surface: `MarketDataProvider`, `PriceCache`, `create_provider`, `PriceStreamHub`, `MarketPoller`, `CacheEntry`, `Direction`, `PriceEvent`, `PriceTick` |
| `base.py` | 43 | `MarketDataProvider` — ABC with abstract `get_prices()`/`validate_ticker()`, optional `start()`/`aclose()` hooks, class attrs `source: str` and `poll_interval: float` |
| `types.py` | 46 | `PriceTick` (provider output), `CacheEntry` (cache row), `PriceEvent` (wire format, has `.to_sse()`), `Direction` literal, `to_iso_z()` helper |
| `cache.py` | 77 | `PriceCache` — thread-safe (`threading.Lock`, not asyncio) latest-price store; `ingest()`, `seed_missing()`, `mark_emitted()`, `snapshot()`, `latest_price()`, `known_tickers()`, `newest_update_age_ms()` |
| `poller.py` | 62 | `MarketPoller` — the *only* code that calls `provider.get_prices()`; drives it on `provider.poll_interval`, unions the live watchlist with everything already cached, writes results into `PriceCache` |
| `hub.py` | 92 | `PriceStreamHub` — fixed 500ms broadcast loop, computes `direction` against the **last value emitted to clients** (not last ingested), pub/sub fan-out over `asyncio.Queue`, drops slow subscribers instead of blocking |
| `simulator.py` | 151 | `SimulatedProvider` + `TickerState` — independent per-ticker GBM; deterministic hash-seeded prices for novel tickers |
| `massive.py` | 174 | `MassiveProvider` — REST polling via raw `httpx.AsyncClient` against `https://api.massive.com`; snapshot parsing with a fallback price chain; 429/5xx backoff |
| `factory.py` | 20 | `create_provider()` — reads `MASSIVE_API_KEY` from the environment (stripped), returns `MassiveProvider` if non-empty else `SimulatedProvider` |

### Key Design Decisions (as implemented, not as originally claimed)

- **Strategy pattern via `MarketDataProvider` ABC** — `SimulatedProvider` and `MassiveProvider` are the only two implementations; nothing downstream is allowed to know which is active except that `/api/health` should report `.source` (`"simulator"` / `"massive"`).
- **`PriceCache` is plain-dict-and-lock, not async** — deliberately synchronous so it's safe to touch from any code path (sync or async, any event loop) without an `await`.
- **`MarketPoller` is the sole caller of the provider.** SSE and any future REST routes are only supposed to read `PriceCache` — this keeps provider-specific quirks (rate limits, polling cadence) out of the request path.
- **`PriceStreamHub` tracks "last emitted," not "last ingested," for direction.** This matters specifically for Massive's free tier (15s poll vs. 500ms broadcast): if direction were computed against the last *ingested* tick, most 500ms broadcast frames between two 15s polls would show `flat` even though the client hasn't seen the newer price yet as `up`/`down`. Tracking last-emitted keeps the diff meaningful regardless of provider polling cadence.
- **Direction is computed on the *rounded* (4dp) values actually sent over the wire**, not the raw floats — otherwise a sub-precision float wobble (e.g. 1e-9) could be labeled `"up"`/`"down"` while the displayed `price` and `previous_price` numbers look identical to the client (a flash with no visible number change). There's a `FLAT_EPSILON = 1e-9` guard band in `direction_of()`.
- **Independent per-ticker GBM only — no correlation, no random "shock" events.** `TickerState.step()` is a plain per-ticker geometric Brownian motion step; each ticker owns its own `random.Random` instance (`rng_for()`) so series are statistically independent of each other, and a `master_seed` parameter (used only in tests) makes runs reproducible — production uses OS entropy. There is no Cholesky decomposition, no sector correlation matrix, and no random shock-event mechanism anywhere in `simulator.py`. (PLAN §6 marks correlation/events as optional stretch scope; this build implements only the required core.)
- **Deterministic seed for novel tickers**: SHA-256 of the uppercased symbol → uniform fraction → mapped into `$15.00–$600.00`, `drift=0.0`, `volatility=0.30` (`deterministic_seed_price()` / `seed_for()`). The 10 PLAN-default tickers use a curated price table instead, with three of them (`TSLA`, `NVDA`, `NFLX`) given higher-volatility overrides; all curated tickers still use `drift=0.0`.
- **`MassiveProvider` talks to the Massive REST API directly via `httpx`** — there is no `massive` PyPI package; `pyproject.toml`'s only runtime dependency is `httpx>=0.27,<1`. `extract_price()` falls through `lastTrade.p → min.c → day.c → prevDay.c`, skipping unusable (`None`/`0`) fields rather than raising. Never raises on malformed/missing data anywhere in the response-parsing path (checked defensively at every JSON-shape assumption); 429 responses honor `Retry-After` (capped at 60s), 5xx enters the same backoff using `poll_interval` as the delay, and 401/403 log and return no data rather than falling back to the simulator mid-process (provider selection is a one-time startup decision per `factory.py`).
- **SSE cadence is fixed and provider-independent**: `PriceStreamHub` broadcasts every `BROADCAST_INTERVAL = 0.5s` regardless of whether the active provider polls every 0.5s (simulator) or 15s (Massive free tier) — this satisfies PLAN §6's requirement to re-emit unchanged prices as `direction: "flat"` on every tick.

## Test Suite

**97 tests, all passing** — verified directly:
```
$ cd backend && uv run pytest tests/market/ -v
...
============================== 97 passed in 0.61s ==============================
```

8 test modules in `backend/tests/market/` (counts from `pytest --collect-only`, includes parametrized cases):

| Module | Tests | Focus |
|--------|------:|-------|
| `test_types.py` | 2 | `to_iso_z()` formatting, `PriceEvent.to_sse()` round-trips as JSON |
| `test_cache.py` | 11 | ingest/seed/mark_emitted semantics, snapshot is a defensive copy, staleness age |
| `test_factory.py` | 4 | key-present/absent/blank/whitespace → correct provider selection |
| `test_hub.py` | 14 | `direction_of()` boundary cases (parametrized), last-emitted vs last-ingested diffing, fan-out, slow-subscriber drop, start/stop |
| `test_poller.py` | 4 | watchlist ∪ known-tickers union, no-op when nothing known, survives a provider exception without dying |
| `test_simulator.py` | 20 | deterministic novel-ticker seeding (incl. a golden value), curated-table lookup + overrides, RNG independence/reproducibility, GBM statistical properties (log-return stdev ≈ σ√dt), price floor never crossed |
| `test_massive.py` | 32 | `extract_price()` fallback chain (parametrized), snapshot parsing, 429/5xx/401/403/non-2xx/malformed-JSON/non-dict-body handling, `validate_ticker()` fail-closed behavior |
| `test_provider_conformance.py` | 10 | both providers, run through shared parametrized cases, satisfy the same `MarketDataProvider` contract (result keys ⊆ requested, never raises on bad input, `start()`/`aclose()` idempotent-enough) |

**No coverage tool is configured** — `pytest-cov` is not in `pyproject.toml`'s dev dependencies, and `--cov` fails with "unrecognized arguments" when attempted. Any coverage percentage for this package would need real tooling added first; none is claimed here.

## Known Gaps

- **No SSE FastAPI route/endpoint exists** (see architecture note above) — `hub.py`'s pub/sub is unconsumed until someone writes the `GET /api/stream/prices` route.
- No demo script exists anywhere in the repo (no `market_data_demo.py`, no Rich terminal dashboard).
- `MassiveProvider`'s poll interval is hardcoded to the free-tier default (15s) in `factory.py` — PLAN §6's "paid tiers: poll every 2–15s depending on tier" isn't configurable yet; the tier can't be detected from the API key alone (noted in a code comment).

*(Previously this section also flagged that `backend/README.md` and a test docstring pointed at a nonexistent `planning/MARKET_DATA_DESIGN.md`. Fixed: both now point at `planning/PLAN.md` §6/§12 and this summary instead.)*

## Usage for Downstream Code

Based on the actual public API in `market/__init__.py`:

```python
from market import MarketPoller, PriceCache, PriceStreamHub, create_provider

# Startup
cache = PriceCache()
provider = create_provider()  # reads MASSIVE_API_KEY
poller = MarketPoller(provider, cache, tickers_supplier=get_watchlist_and_held_tickers)
hub = PriceStreamHub(cache)

await poller.start()   # also calls provider.start() and primes the cache synchronously
await hub.start()      # begins the 500ms broadcast loop

# Somewhere in an SSE route (not yet written):
queue = hub.subscribe()
try:
    while True:
        event = await queue.get()
        yield event.to_sse()
finally:
    hub.unsubscribe(queue)

# Reads (e.g. for /api/portfolio valuation)
price = cache.latest_price("AAPL")   # float or None
age_ms = cache.newest_update_age_ms()  # feeds /api/health staleness check

# Shutdown
await hub.stop()
await poller.stop()   # also calls provider.aclose()
```

Note `tickers_supplier` is a required constructor argument for `MarketPoller` (a zero-arg callable returning the current watchlist) — it is not optional, and downstream code (the not-yet-built watchlist/DB layer) needs to supply it.
