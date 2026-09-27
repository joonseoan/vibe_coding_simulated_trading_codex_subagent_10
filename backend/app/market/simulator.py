"""Independent per-symbol geometric-Brownian-motion provider."""
from __future__ import annotations
import asyncio
import hashlib
import math
import random
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from .base import MarketDataProvider
from .types import PriceTick

UPDATE_INTERVAL_SECONDS = 0.5
DT_YEARS = UPDATE_INTERVAL_SECONDS / (252 * 6.5 * 3600)
TICKER_RE = re.compile(r"^[A-Z][A-Z.\-]{0,9}$")
SEED_PRICES = {"AAPL": 190.0, "GOOGL": 175.0, "MSFT": 415.0, "AMZN": 185.0, "TSLA": 250.0, "NVDA": 120.0, "META": 500.0, "JPM": 200.0, "V": 280.0, "NFLX": 650.0}


def deterministic_seed_price(symbol: str) -> float:
    digest = hashlib.sha256(symbol.upper().encode()).digest()
    return round(15.0 + int.from_bytes(digest[:8], "big") / 2**64 * 585.0, 2)


@dataclass(slots=True)
class _TickerState:
    price: float
    rng: random.Random
    volatility: float = 0.30
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    def step(self) -> None:
        change = -0.5 * self.volatility**2 * DT_YEARS + self.volatility * math.sqrt(DT_YEARS) * self.rng.gauss(0.0, 1.0)
        self.price, self.updated_at = max(self.price * math.exp(change), 0.01), datetime.now(timezone.utc)


class SimulatedProvider(MarketDataProvider):
    source = "simulator"
    def __init__(self, poll_interval: float = UPDATE_INTERVAL_SECONDS, seed: int | None = None) -> None:
        self.poll_interval, self._seed, self._states = poll_interval, seed, {}
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        for ticker in SEED_PRICES: self._ensure(ticker)
        self._task = asyncio.create_task(self._run(), name="simulator")

    async def aclose(self) -> None:
        if self._task:
            self._task.cancel()
            try: await self._task
            except asyncio.CancelledError: pass

    async def get_prices(self, tickers: list[str]) -> dict[str, PriceTick]:
        out: dict[str, PriceTick] = {}
        for raw in tickers:
            symbol = raw.upper().strip()
            if TICKER_RE.fullmatch(symbol):
                state = self._ensure(symbol)
                out[symbol] = PriceTick(symbol, state.price, state.updated_at)
        return out

    async def validate_ticker(self, ticker: str) -> bool:
        return bool(TICKER_RE.fullmatch(ticker.upper().strip()))

    def _ensure(self, symbol: str) -> _TickerState:
        if symbol not in self._states:
            price = SEED_PRICES.get(symbol, deterministic_seed_price(symbol))
            self._states[symbol] = _TickerState(price, random.Random(f"{self._seed}:{symbol}" if self._seed is not None else None))
        return self._states[symbol]

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self.poll_interval)
            for state in list(self._states.values()): state.step()
