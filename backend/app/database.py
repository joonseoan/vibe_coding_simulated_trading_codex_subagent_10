"""SQLite database with lazy initialization."""

import os
import uuid
from datetime import datetime, timezone

import aiosqlite

# The container mounts this directory as a persistent volume. Tests replace
# this module attribute with an isolated temporary database.
DB_PATH = os.environ.get("DB_PATH", "/app/db/simulated_trading.db")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users_profile (
    id TEXT PRIMARY KEY DEFAULT 'default',
    cash_balance REAL DEFAULT 10000.0,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS watchlist (
    id TEXT PRIMARY KEY,
    user_id TEXT DEFAULT 'default',
    ticker TEXT,
    added_at TEXT,
    UNIQUE(user_id, ticker)
);

CREATE TABLE IF NOT EXISTS positions (
    id TEXT PRIMARY KEY,
    user_id TEXT DEFAULT 'default',
    ticker TEXT,
    quantity REAL,
    avg_cost REAL,
    updated_at TEXT,
    UNIQUE(user_id, ticker)
);

CREATE TABLE IF NOT EXISTS trades (
    id TEXT PRIMARY KEY,
    user_id TEXT DEFAULT 'default',
    ticker TEXT,
    side TEXT,
    quantity REAL,
    price REAL,
    executed_at TEXT
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id TEXT PRIMARY KEY,
    user_id TEXT DEFAULT 'default',
    role TEXT,
    content TEXT,
    actions TEXT,
    created_at TEXT
);
"""

DEFAULT_TICKERS = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", "NFLX"]


def utc_now() -> str:
    """Return the canonical persisted timestamp representation."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


async def get_db() -> aiosqlite.Connection:
    """Get a database connection."""
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    return db


async def init_db():
    """Create schema and seed data if needed."""
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)

    db = await get_db()
    try:
        await db.executescript(SCHEMA_SQL)

        # Snapshots are retired by the active contract, including on upgrades.
        await db.execute("DROP TABLE IF EXISTS portfolio_snapshots")

        # Check if seed data exists
        cursor = await db.execute("SELECT COUNT(*) FROM users_profile")
        row = await cursor.fetchone()
        if row[0] == 0:
            now = utc_now()
            await db.execute(
                "INSERT INTO users_profile (id, cash_balance, created_at) VALUES (?, ?, ?)",
                ("default", 10000.0, now),
            )
            for ticker in DEFAULT_TICKERS:
                await db.execute(
                    "INSERT INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
                    (str(uuid.uuid4()), "default", ticker, now),
                )
            await db.commit()
    finally:
        await db.close()
