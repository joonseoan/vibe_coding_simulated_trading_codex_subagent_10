from __future__ import annotations
import dataclasses
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

Direction = Literal["up", "down", "flat"]


def to_iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class PriceTick:
    ticker: str
    price: float
    timestamp: datetime


@dataclass(slots=True)
class CacheEntry:
    price: float
    previous_price: float
    updated_at: datetime
    source_time: datetime


@dataclass(frozen=True, slots=True)
class PriceEvent:
    ticker: str
    price: float
    previous_price: float
    timestamp: str
    direction: Direction

    def to_sse(self) -> str:
        return f"data: {json.dumps(dataclasses.asdict(self))}\n\n"
