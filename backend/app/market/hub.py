from __future__ import annotations
import asyncio
from .cache import PriceCache
from .types import Direction, PriceEvent, to_iso_z

BROADCAST_INTERVAL = 0.5
FLAT_EPSILON = 1e-9
SUBSCRIBER_QUEUE_MAX = 1000


def direction_of(previous: float, current: float) -> Direction:
    if current > previous + FLAT_EPSILON:
        return "up"
    if current < previous - FLAT_EPSILON:
        return "down"
    return "flat"


class PriceStreamHub:
    """Creates the 500ms SSE event stream from cache snapshots."""
    def __init__(self, cache: PriceCache) -> None:
        self._cache = cache
        self._subscribers: set[asyncio.Queue[PriceEvent]] = set()
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="price-stream-hub")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    def subscribe(self) -> asyncio.Queue[PriceEvent]:
        queue: asyncio.Queue[PriceEvent] = asyncio.Queue(maxsize=SUBSCRIBER_QUEUE_MAX)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[PriceEvent]) -> None:
        self._subscribers.discard(queue)

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(BROADCAST_INTERVAL)
            events = self._build_events()
            for queue in tuple(self._subscribers):
                for event in events:
                    try:
                        queue.put_nowait(event)
                    except asyncio.QueueFull:
                        self._subscribers.discard(queue)
                        break

    def _build_events(self) -> list[PriceEvent]:
        events: list[PriceEvent] = []
        for ticker, entry in self._cache.snapshot().items():
            price, previous = round(entry.price, 2), round(entry.previous_price, 2)
            events.append(PriceEvent(ticker, price, previous, to_iso_z(entry.source_time), direction_of(previous, price)))
            self._cache.mark_emitted(ticker, entry.price)
        return events
