"""FastAPI entry point and lifecycle owner for the market services."""
from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.chat import router as chat_router
from app.database import get_db, init_db
from app.market import MarketPoller, PriceCache, PriceStreamHub, create_provider
from app.market.stream import router as stream_router
from app.portfolio import router as portfolio_router
from app.watchlist import router as watchlist_router


class TickerRegistry:
    """Synchronous market ticker supplier, refreshed by application actions."""
    def __init__(self) -> None:
        self._tickers: set[str] = set()

    def snapshot(self) -> list[str]:
        return sorted(self._tickers)

    def add(self, ticker: str) -> None:
        self._tickers.add(ticker.upper().strip())

    def discard(self, ticker: str) -> None:
        self._tickers.discard(ticker.upper().strip())

    async def refresh_from_db(self) -> None:
        db = await get_db()
        try:
            watched = await (await db.execute("SELECT ticker FROM watchlist WHERE user_id = 'default'")).fetchall()
            held = await (await db.execute("SELECT ticker FROM positions WHERE user_id = 'default' AND quantity > 0")).fetchall()
            self._tickers = {row["ticker"].upper().strip() for row in watched + held}
        finally:
            await db.close()


@dataclass(slots=True)
class MarketServices:
    """The single app-owned market dependency bundle for all routes."""
    provider: object
    cache: PriceCache
    poller: MarketPoller
    hub: PriceStreamHub
    ticker_registry: TickerRegistry


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize DB, then start the single injected market service bundle."""
    await init_db()
    registry = TickerRegistry()
    await registry.refresh_from_db()
    cache = PriceCache()
    provider = create_provider()
    poller = MarketPoller(provider, cache, registry.snapshot)
    hub = PriceStreamHub(cache)
    app.state.market_services = MarketServices(provider, cache, poller, hub, registry)
    await poller.start()
    await hub.start()
    try:
        yield
    finally:
        await hub.stop()
        await poller.stop()


app = FastAPI(title="FinAlly", lifespan=lifespan)
app.include_router(chat_router)
app.include_router(stream_router)
app.include_router(portfolio_router)
app.include_router(watchlist_router)


@app.get("/api/health")
async def health():
    """Report database availability and freshness of the canonical price cache."""
    db_status = "ok"
    try:
        db = await get_db()
        try:
            await (await db.execute("SELECT 1")).fetchone()
        finally:
            await db.close()
    except Exception:
        db_status = "error"

    services = getattr(app.state, "market_services", None)
    cache = getattr(services, "cache", None)
    age = cache.newest_update_age_ms() if cache else None
    source = getattr(getattr(services, "provider", None), "source", "unavailable")
    market_feed = {"source": source, "last_update_age_ms": round(age) if age is not None else None}
    if db_status != "ok" or age is None or age > 10_000:
        return JSONResponse(status_code=503, content={"status": "degraded", "db": db_status, "market_feed": market_feed})
    return JSONResponse({"status": "ok", "db": db_status, "market_feed": market_feed})


static_dir = Path(__file__).parent.parent.parent / "static"
if static_dir.is_dir():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
