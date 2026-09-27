# Simulated Trading - the Finance Ally

All project documentation is in the `planning` directory.

The key document is PLAN.md included in full below; the market data provider/cache/poller layer (`backend/market/`) is complete and tested (97/97 passing) and is summarized in the file planning/MARKET_DATA_SUMMARY.md, with earlier superseded design drafts kept for history in the planning/archive folder. Note: no FastAPI app or SSE route exists yet, so `GET /api/stream/prices` is not wired up — that remains open work. Consult these docs only when required. The remainder of the platform is still to be developed.

@planning/PLAN.md
