from __future__ import annotations
import asyncio
import logging
from collections.abc import Callable
from .base import MarketDataProvider
from .cache import PriceCache

log = logging.getLogger("market.poller")


class MarketPoller:
    """The sole provider caller, writing provider observations into the cache."""
    def __init__(self, provider: MarketDataProvider, cache: PriceCache, tickers_supplier: Callable[[], list[str]]) -> None:
        self._provider, self._cache, self._tickers_supplier = provider, cache, tickers_supplier
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        await self._provider.start()
        await self._poll_once()
        self._task = asyncio.create_task(self._run(), name="market-poller")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self._provider.aclose()

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self._provider.poll_interval)
            try:
                await self._poll_once()
            except Exception:
                log.exception("market poll cycle failed; retaining cached prices")

    async def _poll_once(self) -> None:
        tickers = sorted(set(self._tickers_supplier()) | self._cache.known_tickers())
        if not tickers:
            return
        for tick in (await self._provider.get_prices(tickers)).values():
            self._cache.ingest(tick)
