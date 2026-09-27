"""Chat routes backed by the same portfolio and watchlist services as the UI."""
from __future__ import annotations

import json
import os
import uuid
from typing import Any, Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from litellm import acompletion
from pydantic import BaseModel, Field

from app.database import get_db, utc_now
from app.services import DomainError, add_watchlist_item, error_body, execute_trade, read_portfolio, remove_watchlist_item

router = APIRouter()


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class RequestedTrade(BaseModel):
    ticker: str
    side: Literal["buy", "sell"]
    quantity: float


class RequestedWatchlistChange(BaseModel):
    ticker: str
    action: Literal["add", "remove"]


class ModelReply(BaseModel):
    message: str
    trades: list[RequestedTrade] = Field(default_factory=list)
    watchlist_changes: list[RequestedWatchlistChange] = Field(default_factory=list)


SYSTEM_PROMPT = """You are FinAlly, a concise simulated-trading assistant.
Return JSON with message, trades [{ticker, side, quantity}], and
watchlist_changes [{ticker, action}]. Execute actions only when explicitly asked."""


def _bundle(request: Request) -> Any:
    bundle = getattr(request.app.state, "market_services", None)
    if bundle is None:
        raise DomainError("market_unavailable", "Market data is not available.", 503)
    return bundle


def _failure(error: DomainError) -> JSONResponse:
    return JSONResponse(error_body(error), status_code=error.status_code)


async def _history_for_prompt(db: Any) -> list[dict[str, str]]:
    cur = await db.execute("SELECT role, content FROM chat_messages WHERE user_id = 'default' ORDER BY created_at DESC, rowid DESC LIMIT 20")
    return [{"role": row["role"], "content": row["content"]} for row in reversed(await cur.fetchall())]


def _mock_reply(message: str) -> ModelReply:
    lower = message.lower()
    tickers = ("AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", "NFLX")
    ticker = next((item for item in tickers if item.lower() in lower), "AAPL")
    if "buy" in lower:
        return ModelReply(message=f"Buying 10 shares of {ticker}.", trades=[RequestedTrade(ticker=ticker, side="buy", quantity=10)])
    if "sell" in lower:
        return ModelReply(message=f"Selling 10 shares of {ticker}.", trades=[RequestedTrade(ticker=ticker, side="sell", quantity=10)])
    if "remove" in lower:
        return ModelReply(message="Removing NFLX from your watchlist.", watchlist_changes=[RequestedWatchlistChange(ticker="NFLX", action="remove")])
    if "watch" in lower or "add" in lower:
        return ModelReply(message="Adding PYPL to your watchlist.", watchlist_changes=[RequestedWatchlistChange(ticker="PYPL", action="add")])
    if "portfolio" in lower or "position" in lower or "holding" in lower:
        return ModelReply(message="Here is your current portfolio summary.")
    return ModelReply(message="I can analyze your portfolio, place simulated trades, or manage your watchlist.")


async def _call_llm(messages: list[dict[str, str]]) -> ModelReply:
    response = await acompletion(model="openrouter/openai/gpt-oss-120b", messages=messages, extra_body={"response_format": {"type": "json_object"}})
    return ModelReply.model_validate(json.loads(response.choices[0].message.content))


@router.get("/api/chat/history")
async def chat_history():
    db = await get_db()
    try:
        cur = await db.execute("SELECT id, role, content, actions, created_at FROM chat_messages WHERE user_id = 'default' ORDER BY created_at DESC, rowid DESC LIMIT 20")
        rows = list(reversed(await cur.fetchall()))
        return [{"id": row["id"], "role": row["role"], "content": row["content"], "actions": json.loads(row["actions"]) if row["actions"] else None, "created_at": row["created_at"]} for row in rows]
    finally:
        await db.close()


@router.post("/api/chat")
async def chat(request: Request, req: ChatRequest):
    if not req.message.strip():
        return _failure(DomainError("invalid_message", "Message must not be blank."))
    try:
        bundle = _bundle(request)
        db = await get_db()
        try:
            if os.environ.get("LLM_MOCK", "").lower() == "true":
                reply = _mock_reply(req.message)
            else:
                if not os.environ.get("OPENROUTER_API_KEY", "").strip():
                    raise DomainError("llm_not_configured", "LLM not configured: set OPENROUTER_API_KEY or LLM_MOCK=true.", 503)
                portfolio = await read_portfolio(db, bundle.cache)
                messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "system", "content": f"Current portfolio: {json.dumps(portfolio)}"}, *await _history_for_prompt(db), {"role": "user", "content": req.message}]
                try:
                    reply = await _call_llm(messages)
                except Exception as exc:
                    raise DomainError("llm_unavailable", "The trading assistant is temporarily unavailable.", 503) from exc

            actions: dict[str, list[dict[str, Any]]] = {"trades": [], "watchlist_changes": []}
            for action in reply.trades:
                try:
                    result = await execute_trade(db, bundle.cache, action.ticker, action.side, action.quantity)
                    actions["trades"].append({"ticker": result["trade"]["ticker"], "side": action.side, "quantity": action.quantity, "status": "filled", "price": result["trade"]["price"], "error": None})
                except DomainError as error:
                    actions["trades"].append({"ticker": action.ticker.upper().strip(), "side": action.side, "quantity": action.quantity, "status": "rejected", "price": None, "error": error.code})
            for action in reply.watchlist_changes:
                try:
                    if action.action == "add":
                        await add_watchlist_item(db, action.ticker, bundle.provider.validate_ticker)
                    else:
                        await remove_watchlist_item(db, action.ticker)
                    actions["watchlist_changes"].append({"ticker": action.ticker.upper().strip(), "action": action.action, "status": "applied", "error": None})
                except DomainError as error:
                    actions["watchlist_changes"].append({"ticker": action.ticker.upper().strip(), "action": action.action, "status": "rejected", "error": error.code})

            await bundle.ticker_registry.refresh_from_db()
            portfolio = await read_portfolio(db, bundle.cache)
            await db.execute("INSERT INTO chat_messages (id, user_id, role, content, actions, created_at) VALUES (?, 'default', 'user', ?, NULL, ?)", (str(uuid.uuid4()), req.message.strip(), utc_now()))
            await db.execute("INSERT INTO chat_messages (id, user_id, role, content, actions, created_at) VALUES (?, 'default', 'assistant', ?, ?, ?)", (str(uuid.uuid4()), reply.message, json.dumps(actions), utc_now()))
            await db.commit()
            return {"message": reply.message, "actions": actions, "portfolio": portfolio}
        except Exception:
            await db.rollback()
            raise
        finally:
            await db.close()
    except DomainError as error:
        return _failure(error)
