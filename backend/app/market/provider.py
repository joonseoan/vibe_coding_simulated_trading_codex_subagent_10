"""Environment-driven provider selection."""
from __future__ import annotations
import os
from .base import MarketDataProvider


def create_provider() -> MarketDataProvider:
    key = os.environ.get("MASSIVE_API_KEY", "").strip()
    if key:
        from .massive import MassiveProvider
        return MassiveProvider(key)
    from .simulator import SimulatedProvider
    return SimulatedProvider()
