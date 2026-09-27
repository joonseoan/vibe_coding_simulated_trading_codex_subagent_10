# Simulated Trading — AI Trading Workstation

A Bloomberg-style terminal for a simulated $10,000 portfolio: streaming prices,
market-order trading with fractional shares, live charts (sparklines, main chart,
portfolio heatmap, session P&L), and an LLM assistant that analyzes positions and
executes trades on your behalf. No login.

Built by orchestrated coding agents as the capstone for an agentic AI coding course.

> **Status:** implemented. The current market-data and API contract is in
> [`planning/MILESTONE_1_MARKET_AND_API_CONTRACT.md`](planning/MILESTONE_1_MARKET_AND_API_CONTRACT.md).

## Stack

One Docker container on port 8000: Next.js static export (Tailwind + Recharts) served
by FastAPI (Python/`uv`), SQLite (WAL) bind-mounted at `./db/`, live prices over SSE.
Market data comes from a built-in GBM simulator, or the Massive/Polygon API when
`MASSIVE_API_KEY` is set. AI runs through LiteLLM → OpenRouter
(`openai/gpt-oss-120b` on Cerebras) with structured outputs. All charts accumulate
client-side from the stream since page load — no historical backfill.

## Run

```bash
cp .env.example .env      # set OPENROUTER_API_KEY, or LLM_MOCK=true
./scripts/start_mac.sh --build
```

Use `--build` whenever the source has changed or you pulled newer code. Without it,
the script reuses an existing local `finally` Docker image, which may serve an older
version of the application. Once it starts, open <http://localhost:8000>.

For later starts when the source has not changed, this is sufficient:

```bash
./scripts/start_mac.sh
```

Windows users can run `scripts/start_windows.ps1`; Compose users can run
`docker compose up --build`. Stop with `./scripts/stop_mac.sh`; add `--wipe` to also
clear the local simulation database.

## Environment

| Variable | Required | Purpose |
|---|---|---|
| `OPENROUTER_API_KEY` | unless `LLM_MOCK=true` | LLM chat; without it the app runs but `/api/chat` returns `503` |
| `MASSIVE_API_KEY` | no | real market data; unset → simulator |
| `LLM_MOCK` | no | `true` → deterministic mock LLM responses for tests / no-key dev |

## Layout

```
frontend/   Next.js static-export app
backend/    FastAPI uv project — API, SSE, market data, LLM, schema + seed
planning/   PLAN.md, the shared spec for all agents
scripts/    start/stop entry points
test/       Playwright E2E (docker-compose.test.yml)
db/         runtime bind-mount for simulated_trading.db (gitignored)
```
