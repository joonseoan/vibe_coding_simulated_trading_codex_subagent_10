"""High-value API contract tests using the real FastAPI lifespan."""
import os

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def live_client(db, monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "true")
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client


@pytest.mark.asyncio
async def test_health_and_portfolio_contract(live_client):
    health = await live_client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["market_feed"]["source"] == "simulator"
    portfolio = await live_client.get("/api/portfolio")
    assert portfolio.json() == {"cash_balance": 10000.0, "total_value": 10000.0, "positions": []}


@pytest.mark.asyncio
async def test_trade_blotter_reset_and_chat_history(live_client):
    trade = await live_client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 0.5, "side": "buy"})
    assert trade.status_code == 200
    assert trade.json()["trade"]["quantity"] == 0.5
    assert len((await live_client.get("/api/portfolio/trades")).json()) == 1
    chat = await live_client.post("/api/chat", json={"message": "buy AAPL"})
    assert chat.status_code == 200
    assert chat.json()["actions"]["trades"][0]["status"] == "filled"
    history = await live_client.get("/api/chat/history")
    assert len(history.json()) == 2
    reset = await live_client.post("/api/portfolio/reset")
    assert reset.status_code == 200
    assert reset.json()["portfolio"]["positions"] == []
    assert len(reset.json()["watchlist"]) == 10
