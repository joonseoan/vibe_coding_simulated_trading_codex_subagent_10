"""Robust pull-only client for Massive's stock snapshot API."""
from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone
import httpx
from .base import MarketDataProvider
from .types import PriceTick

log = logging.getLogger("market.massive")
BASE_URL = "https://api.massive.com"
SNAPSHOT_PATH = "/v2/snapshot/locale/us/markets/stocks/tickers"
SINGLE_SNAPSHOT_PATH = SNAPSHOT_PATH + "/{ticker}"

def extract_price(item: dict) -> float | None:
    for section, field in (("lastTrade", "p"), ("min", "c"), ("day", "c"), ("prevDay", "c")):
        value = item.get(section)
        if isinstance(value, dict) and value.get(field): return float(value[field])
    return None

class MassiveProvider(MarketDataProvider):
    source = "massive"
    def __init__(self, api_key: str, poll_interval: float = 15.0, base_url: str = BASE_URL) -> None:
        self.poll_interval = poll_interval
        self._client = httpx.AsyncClient(base_url=base_url, headers={"Authorization": f"Bearer {api_key}"}, timeout=httpx.Timeout(10.0, connect=5.0))
        self._backoff_until = 0.0

    async def aclose(self) -> None: await self._client.aclose()

    async def get_prices(self, tickers: list[str]) -> dict[str, PriceTick]:
        if not tickers or asyncio.get_running_loop().time() < self._backoff_until: return {}
        loop = asyncio.get_running_loop()
        try: response = await self._client.get(SNAPSHOT_PATH, params={"tickers": ",".join(sorted({ticker.upper() for ticker in tickers}))})
        except httpx.HTTPError:
            log.exception("massive snapshot request failed")
            return {}
        if response.status_code == 429 or response.status_code >= 500:
            try: delay = float(response.headers.get("Retry-After", self.poll_interval))
            except ValueError: delay = self.poll_interval
            self._backoff_until = loop.time() + min(delay, 60.0)
            return {}
        if response.status_code != 200:
            log.error("massive snapshot status %s", response.status_code)
            return {}
        try: payload = response.json()
        except ValueError:
            log.exception("massive snapshot invalid JSON")
            return {}
        items = payload.get("tickers") if isinstance(payload, dict) else None
        if not isinstance(items, list): return {}
        now, result = datetime.now(timezone.utc), {}
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("ticker"), str): continue
            price = extract_price(item)
            if price is None: continue
            stamp = item.get("updated")
            timestamp = datetime.fromtimestamp(stamp / 1_000_000_000, tz=timezone.utc) if isinstance(stamp, int) else now
            symbol = item["ticker"].upper()
            result[symbol] = PriceTick(symbol, price, timestamp)
        return result

    async def validate_ticker(self, ticker: str) -> bool:
        try: response = await self._client.get(SINGLE_SNAPSHOT_PATH.format(ticker=ticker.upper().strip()))
        except httpx.HTTPError:
            log.exception("massive ticker validation failed")
            return False
        if response.status_code != 200: return False
        try: payload = response.json()
        except ValueError: return False
        return isinstance(payload, dict) and isinstance(payload.get("ticker"), dict) and extract_price(payload["ticker"]) is not None
