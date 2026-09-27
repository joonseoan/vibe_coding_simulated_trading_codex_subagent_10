"""Portfolio REST endpoints backed by shared transactional services."""

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.database import get_db
from app.services import DomainError, error_body, execute_trade, list_trades, list_watchlist, read_portfolio, reset_account

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


class TradeRequest(BaseModel):
    ticker: str
    quantity: float
    side: str


def _cache(request: Request) -> Any:
    """Get the injected canonical cache; routes never create a global cache."""
    bundle = getattr(request.app.state, "market_services", None)
    cache = getattr(bundle, "cache", None) if bundle else None
    if cache is None:
        raise DomainError("market_unavailable", "Market data is not available.", 503)
    return cache


def _failure(error: DomainError) -> JSONResponse:
    return JSONResponse(error_body(error), status_code=error.status_code)


@router.get("")
async def get_portfolio(request: Request):
    try:
        db = await get_db()
        try:
            return await read_portfolio(db, _cache(request))
        finally:
            await db.close()
    except DomainError as error:
        return _failure(error)


@router.post("/trade")
async def trade(body: TradeRequest, request: Request):
    try:
        db = await get_db()
        try:
            result = await execute_trade(db, _cache(request), body.ticker, body.side, body.quantity)
            await db.commit()
            await request.app.state.market_services.ticker_registry.refresh_from_db()
            return result
        except DomainError:
            await db.rollback()
            raise
        finally:
            await db.close()
    except DomainError as error:
        return _failure(error)


@router.get("/trades")
async def trades():
    db = await get_db()
    try:
        return await list_trades(db)
    finally:
        await db.close()


@router.post("/reset")
async def reset(request: Request):
    try:
        db = await get_db()
        try:
            await reset_account(db)
            await db.commit()
            await request.app.state.market_services.ticker_registry.refresh_from_db()
            return {"ok": True, "portfolio": await read_portfolio(db, _cache(request)), "watchlist": await list_watchlist(db)}
        except Exception:
            await db.rollback()
            raise
        finally:
            await db.close()
    except DomainError as error:
        return _failure(error)
