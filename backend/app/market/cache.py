"""Thread-safe, injected latest-price cache."""
from __future__ import annotations
import threading
from datetime import datetime, timezone
from .types import CacheEntry, PriceTick


class PriceCache:
    """The cache owns observations; the stream hub owns emission history."""
    def __init__(self) -> None:
        self._entries: dict[str, CacheEntry] = {}
        self._lock = threading.Lock()

    def known_tickers(self) -> set[str]:
        with self._lock: return set(self._entries)

    def has(self, ticker: str) -> bool:
        with self._lock: return ticker.upper().strip() in self._entries

    def ingest(self, tick: PriceTick) -> None:
        ticker, now = tick.ticker.upper().strip(), datetime.now(timezone.utc)
        with self._lock:
            prior = self._entries.get(ticker)
            self._entries[ticker] = CacheEntry(float(tick.price), prior.previous_price if prior else float(tick.price), now, tick.timestamp)

    def seed_missing(self, ticker: str, price: float) -> None:
        ticker, now = ticker.upper().strip(), datetime.now(timezone.utc)
        with self._lock: self._entries.setdefault(ticker, CacheEntry(price, price, now, now))

    def mark_emitted(self, ticker: str, emitted_price: float) -> None:
        with self._lock:
            if entry := self._entries.get(ticker): entry.previous_price = emitted_price

    def snapshot(self) -> dict[str, CacheEntry]:
        with self._lock:
            return {key: CacheEntry(value.price, value.previous_price, value.updated_at, value.source_time) for key, value in self._entries.items()}

    def latest_price(self, ticker: str) -> float | None:
        with self._lock:
            entry = self._entries.get(ticker.upper().strip())
            return entry.price if entry else None

    def newest_update_age_ms(self) -> float | None:
        with self._lock:
            if not self._entries: return None
            newest = max(item.updated_at for item in self._entries.values())
        return (datetime.now(timezone.utc) - newest).total_seconds() * 1000
