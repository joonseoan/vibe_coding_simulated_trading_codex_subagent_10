"""SSE route backed by the app-owned PriceStreamHub."""
from __future__ import annotations
from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

router = APIRouter()

@router.get("/api/stream/prices")
async def stream_prices(request: Request) -> EventSourceResponse:
    hub = request.app.state.market_services.hub
    queue = hub.subscribe()
    async def events():
        try:
            while True:
                event = await queue.get()
                yield {"event": "price", "data": event.to_sse()[6:-2]}
        finally:
            hub.unsubscribe(queue)
    return EventSourceResponse(events())
