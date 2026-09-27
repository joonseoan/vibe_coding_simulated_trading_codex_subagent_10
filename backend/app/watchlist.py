"""Watchlist REST endpoints; prices are deliberately streamed, not embedded."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.database import get_db
from app.services import DomainError, add_watchlist_item, error_body, list_watchlist, remove_watchlist_item

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


class AddTickerRequest(BaseModel):
    ticker: str


def _validator(request: Request):
    bundle = getattr(request.app.state, "market_services", None)
    provider = getattr(bundle, "provider", None) if bundle else None
    validate = getattr(provider, "validate_ticker", None)
    if validate is None:
        raise DomainError("market_unavailable", "Ticker validation is unavailable.", 503)
    return validate


def _failure(error: DomainError) -> JSONResponse:
    return JSONResponse(error_body(error), status_code=error.status_code)


@router.get("")
async def get_watchlist():
    db = await get_db()
    try:
        return await list_watchlist(db)
    finally:
        await db.close()


@router.post("")
async def add_ticker(body: AddTickerRequest, request: Request):
    try:
        db = await get_db()
        try:
            item = await add_watchlist_item(db, body.ticker, _validator(request))
            await db.commit()
            await request.app.state.market_services.ticker_registry.refresh_from_db()
            return item
        except DomainError:
            await db.rollback()
            raise
        finally:
            await db.close()
    except DomainError as error:
        return _failure(error)


@router.delete("/{ticker}")
async def remove_ticker(ticker: str, request: Request):
    try:
        db = await get_db()
        try:
            await remove_watchlist_item(db, ticker)
            await db.commit()
            await request.app.state.market_services.ticker_registry.refresh_from_db()
            return {"ok": True}
        except DomainError:
            await db.rollback()
            raise
        finally:
            await db.close()
    except DomainError as error:
        return _failure(error)
