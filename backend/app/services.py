"""Shared business services for portfolio and watchlist actions.

Routes and chat deliberately use these functions rather than maintaining
separate SQL implementations. Market dependencies are passed in so the app
lifespan can own the one canonical cache/provider bundle.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from app.database import DEFAULT_TICKERS, utc_now

USER_ID = "default"
MIN_QUANTITY = 0.0001
POSITION_EPSILON = 0.00000001
MAX_WATCHLIST_SIZE = 30


class PriceLookup(Protocol):
    def latest_price(self, ticker: str) -> float | None: ...


TickerValidator = Callable[[str], Awaitable[bool]]


class DomainError(Exception):
    """A stable, user-facing domain failure suitable for API error envelopes."""

    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def normalize_ticker(ticker: str) -> str:
    return ticker.upper().strip()


def error_body(error: DomainError) -> dict[str, dict[str, str]]:
    return {"error": {"code": error.code, "message": error.message}}


def _latest_price(cache: PriceLookup, ticker: str) -> float | None:
    """Read the current value from the canonical cache.

    ``latest_price`` is the canonical cache API.  The small ``get`` fallback
    keeps the service usable with an adapter in focused unit tests.
    """
    latest = getattr(cache, "latest_price", None)
    if latest is not None:
        return latest(ticker)
    entry = cache.get(ticker)  # type: ignore[attr-defined]
    return entry.price if entry is not None else None


def _price(cache: PriceLookup, ticker: str) -> float:
    price = _latest_price(cache, ticker)
    if price is None:
        raise DomainError("unknown_ticker", f"No market price is available for {ticker}.")
    return round(float(price), 2)


async def read_portfolio(db: Any, cache: PriceLookup) -> dict[str, Any]:
    cur = await db.execute("SELECT cash_balance FROM users_profile WHERE id = ?", (USER_ID,))
    profile = await cur.fetchone()
    cash = float(profile["cash_balance"] if profile else 10000.0)
    cur = await db.execute("SELECT ticker, quantity, avg_cost FROM positions WHERE user_id = ? ORDER BY ticker", (USER_ID,))
    rows = await cur.fetchall()
    positions, total = [], cash
    for row in rows:
        average, quantity = float(row["avg_cost"]), float(row["quantity"])
        price = _latest_price(cache, row["ticker"])
        price = round(float(price), 2) if price is not None else round(average, 2)
        pnl = (price - average) * quantity
        positions.append({"ticker": row["ticker"], "quantity": quantity, "avg_cost": round(average, 2), "current_price": price, "unrealized_pnl": round(pnl, 2), "pnl_percent": round(((price - average) / average * 100) if average else 0, 2)})
        total += price * quantity
    return {"cash_balance": round(cash, 2), "total_value": round(total, 2), "positions": positions}


async def execute_trade(db: Any, cache: PriceLookup, ticker: str, side: str, quantity: float) -> dict[str, Any]:
    """Mutate cash/positions and write exactly one audit record (no commit)."""
    ticker, side = normalize_ticker(ticker), side.lower().strip()
    if side not in {"buy", "sell"}:
        raise DomainError("invalid_quantity", "Side must be 'buy' or 'sell'.")
    if quantity < MIN_QUANTITY:
        raise DomainError("invalid_quantity", "Quantity must be at least 0.0001.")
    price = _price(cache, ticker)
    cur = await db.execute("SELECT cash_balance FROM users_profile WHERE id = ?", (USER_ID,))
    cash = float((await cur.fetchone())["cash_balance"])
    now = utc_now()
    cur = await db.execute("SELECT quantity, avg_cost FROM positions WHERE user_id = ? AND ticker = ?", (USER_ID, ticker))
    position = await cur.fetchone()

    if side == "buy":
        cost = quantity * price
        if cost > cash + POSITION_EPSILON:
            raise DomainError("insufficient_cash", "Insufficient cash for this trade.")
        if position:
            old_quantity, old_cost = float(position["quantity"]), float(position["avg_cost"])
            new_quantity = old_quantity + quantity
            avg_cost = ((old_quantity * old_cost) + cost) / new_quantity
            await db.execute("UPDATE positions SET quantity = ?, avg_cost = ?, updated_at = ? WHERE user_id = ? AND ticker = ?", (new_quantity, avg_cost, now, USER_ID, ticker))
        else:
            new_quantity, avg_cost = quantity, price
            await db.execute("INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at) VALUES (?, ?, ?, ?, ?, ?)", (str(uuid.uuid4()), USER_ID, ticker, new_quantity, avg_cost, now))
        await db.execute("UPDATE users_profile SET cash_balance = cash_balance - ? WHERE id = ?", (cost, USER_ID))
    else:
        held = float(position["quantity"]) if position else 0.0
        if not position or quantity > held + POSITION_EPSILON:
            raise DomainError("insufficient_shares", "Insufficient shares for this trade.")
        new_quantity = held - quantity
        if new_quantity <= POSITION_EPSILON:
            await db.execute("DELETE FROM positions WHERE user_id = ? AND ticker = ?", (USER_ID, ticker))
            position_result = None
        else:
            await db.execute("UPDATE positions SET quantity = ?, updated_at = ? WHERE user_id = ? AND ticker = ?", (new_quantity, now, USER_ID, ticker))
            position_result = {"ticker": ticker, "quantity": new_quantity, "avg_cost": round(float(position["avg_cost"]), 2)}
        await db.execute("UPDATE users_profile SET cash_balance = cash_balance + ? WHERE id = ?", (quantity * price, USER_ID))

    trade = {"id": str(uuid.uuid4()), "ticker": ticker, "side": side, "quantity": quantity, "price": price, "executed_at": now}
    await db.execute("INSERT INTO trades (id, user_id, ticker, side, quantity, price, executed_at) VALUES (?, ?, ?, ?, ?, ?, ?)", (trade["id"], USER_ID, ticker, side, quantity, price, now))
    if side == "buy":
        position_result = {"ticker": ticker, "quantity": new_quantity, "avg_cost": round(avg_cost, 2)}
    cur = await db.execute("SELECT cash_balance FROM users_profile WHERE id = ?", (USER_ID,))
    balance = float((await cur.fetchone())["cash_balance"])
    return {"trade": trade, "cash_balance": round(balance, 2), "position": position_result}


async def list_trades(db: Any) -> list[dict[str, Any]]:
    cur = await db.execute("SELECT id, ticker, side, quantity, price, executed_at FROM trades WHERE user_id = ? ORDER BY executed_at DESC, rowid DESC", (USER_ID,))
    return [dict(row) for row in await cur.fetchall()]


async def list_watchlist(db: Any) -> list[dict[str, str]]:
    cur = await db.execute("SELECT ticker, added_at FROM watchlist WHERE user_id = ? ORDER BY added_at, rowid", (USER_ID,))
    return [dict(row) for row in await cur.fetchall()]


async def add_watchlist_item(db: Any, ticker: str, validate_ticker: TickerValidator) -> dict[str, str]:
    ticker = normalize_ticker(ticker)
    if not ticker:
        raise DomainError("unknown_ticker", "Ticker is required.")
    cur = await db.execute("SELECT ticker, added_at FROM watchlist WHERE user_id = ? AND ticker = ?", (USER_ID, ticker))
    existing = await cur.fetchone()
    if existing:
        return dict(existing)
    cur = await db.execute("SELECT COUNT(*) AS count FROM watchlist WHERE user_id = ?", (USER_ID,))
    if int((await cur.fetchone())["count"]) >= MAX_WATCHLIST_SIZE:
        raise DomainError("watchlist_full", "The watchlist can contain at most 30 tickers.")
    if not await validate_ticker(ticker):
        raise DomainError("unknown_ticker", f"{ticker} is not a recognized ticker.")
    item = {"ticker": ticker, "added_at": utc_now()}
    await db.execute("INSERT INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)", (str(uuid.uuid4()), USER_ID, ticker, item["added_at"]))
    return item


async def remove_watchlist_item(db: Any, ticker: str) -> None:
    cur = await db.execute("DELETE FROM watchlist WHERE user_id = ? AND ticker = ?", (USER_ID, normalize_ticker(ticker)))
    if cur.rowcount == 0:
        raise DomainError("not_found", "Ticker is not in the watchlist.", 404)


async def reset_account(db: Any) -> None:
    """Reset all user-owned mutable state atomically (caller commits)."""
    now = utc_now()
    await db.execute("UPDATE users_profile SET cash_balance = ? WHERE id = ?", (10000.0, USER_ID))
    for table in ("positions", "trades", "chat_messages", "watchlist"):
        await db.execute(f"DELETE FROM {table} WHERE user_id = ?", (USER_ID,))
    for ticker in DEFAULT_TICKERS:
        await db.execute("INSERT INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)", (str(uuid.uuid4()), USER_ID, ticker, now))
