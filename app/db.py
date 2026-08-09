"""
Database layer — async SQLite via aiosqlite.

Creates `data/agent.db` on first call and ensures the posts table exists.
All queries go through the helpers here so the rest of the app never
touches raw SQL.
"""

from __future__ import annotations

# pyrefly: ignore [missing-import]
import aiosqlite
import os
from pathlib import Path

DB_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DB_DIR / "agent.db"

_CREATE_POSTS_TABLE = """
CREATE TABLE IF NOT EXISTS posts (
    id          TEXT PRIMARY KEY,
    agent_id    TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    text        TEXT NOT NULL,
    rationale   TEXT NOT NULL,
    sources     TEXT NOT NULL,       -- JSON array of URLs
    topic_hash  TEXT NOT NULL,       -- short hash for dedup
    title       TEXT NOT NULL DEFAULT ''
);
"""

_CREATE_REJECTIONS_TABLE = """
CREATE TABLE IF NOT EXISTS rejections (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id    TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    title       TEXT NOT NULL,
    url         TEXT NOT NULL,
    reason      TEXT NOT NULL
);
"""

_CREATE_AGENTS_TABLE = """
CREATE TABLE IF NOT EXISTS agents (
    agent_id    TEXT PRIMARY KEY,
    persona_name TEXT NOT NULL,
    persona_domain TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
"""


from contextlib import asynccontextmanager

async def get_db() -> aiosqlite.Connection:
    """Return an open connection (caller must close or use `async with`)."""
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = await aiosqlite.connect(str(DB_PATH))
    conn.row_factory = aiosqlite.Row
    return conn


@asynccontextmanager
async def get_db_conn():
    """Safe database context manager that prevents double connection initialization issues on newer python versions."""
    conn = await get_db()
    try:
        yield conn
    finally:
        await conn.close()


async def init_db() -> None:
    """Ensure all tables exist."""
    async with get_db_conn() as db:
        await db.execute(_CREATE_POSTS_TABLE)
        await db.execute(_CREATE_REJECTIONS_TABLE)
        await db.execute(_CREATE_AGENTS_TABLE)
        await db.commit()
