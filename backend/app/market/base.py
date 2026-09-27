"""Provider boundary for the injected market-data subsystem."""

from __future__ import annotations
import abc
from .types import PriceTick


class MarketDataProvider(abc.ABC):
    """Pull-only market data source; the poller is its sole caller."""
    source: str
    poll_interval: float

    @abc.abstractmethod
    async def get_prices(self, tickers: list[str]) -> dict[str, PriceTick]:
        """Return a partial ticker-to-price mapping without raising upstream errors."""

    @abc.abstractmethod
    async def validate_ticker(self, ticker: str) -> bool:
        """Return whether a symbol can be resolved by this provider."""

    async def start(self) -> None:
        pass

    async def aclose(self) -> None:
        pass
