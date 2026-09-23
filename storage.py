"""
WerkZoeker — Storage Module (SQLite / aiosqlite)

Handles:
  - Database initialisation
  - Deduplication (check if job ID already exists)
  - Saving new jobs with their filter score and matched keywords
  - Marking jobs as notified
  - Statistics queries
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiosqlite
from loguru import logger

from scrapers.base import JobItem

# ---------------------------------------------------------------------------
# SQL Statements
# ---------------------------------------------------------------------------

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS found_jobs (
    id           TEXT    PRIMARY KEY,
    title        TEXT    NOT NULL,
    source       TEXT    NOT NULL,
    url          TEXT    NOT NULL,
    score        INTEGER NOT NULL DEFAULT 0,
    match_reasons TEXT   NOT NULL DEFAULT '[]',  -- JSON array of matched keywords
    location     TEXT,
    rate_or_hours TEXT,
    created_at   TEXT    NOT NULL,
    notified     INTEGER NOT NULL DEFAULT 0      -- 0 = pending, 1 = notified
);
"""

CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_found_jobs_notified
    ON found_jobs (notified, created_at DESC);
"""

INSERT_JOB_SQL = """
INSERT OR IGNORE INTO found_jobs
    (id, title, source, url, score, match_reasons, location, rate_or_hours, created_at, notified)
VALUES
    (?, ?, ?, ?, ?, ?, ?, ?, ?, 0);
"""

MARK_NOTIFIED_SQL = """
UPDATE found_jobs SET notified = 1 WHERE id = ?;
"""

IS_NEW_SQL = """
SELECT 1 FROM found_jobs WHERE id = ? LIMIT 1;
"""

STATS_SQL = """
SELECT
    COUNT(*)                                    AS total,
    SUM(CASE WHEN notified = 1 THEN 1 ELSE 0 END) AS notified_count,
    SUM(CASE WHEN notified = 0 THEN 1 ELSE 0 END) AS pending_count
FROM found_jobs;
"""

RECENT_JOBS_SQL = """
SELECT id, title, source, url, score, match_reasons, location, rate_or_hours, created_at, notified
FROM found_jobs
ORDER BY created_at DESC
LIMIT ?;
"""


# ---------------------------------------------------------------------------
# Storage Class
# ---------------------------------------------------------------------------

class Storage:
    """
    Async SQLite storage for WerkZoeker.

    Usage:
        async with Storage("jobs.db") as db:
            if await db.is_new(job.id):
                await db.save_job(job, score=10, reasons=["eplan", "hoogspanning"])
                await db.mark_notified(job.id)
    """

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or os.getenv("DB_PATH", "jobs.db")
        self._conn: Optional[aiosqlite.Connection] = None

    async def __aenter__(self) -> "Storage":
        await self.connect()
        return self

    async def __aexit__(self, *args) -> None:
        await self.close()

    async def connect(self) -> None:
        """Open the database connection and ensure schema is created."""
        path = Path(self.db_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        self._conn = await aiosqlite.connect(str(path))
        # Enable WAL mode for better concurrent read/write performance
        await self._conn.execute("PRAGMA journal_mode=WAL;")
        await self._conn.execute("PRAGMA synchronous=NORMAL;")
        await self._conn.execute(CREATE_TABLE_SQL)
        await self._conn.execute(CREATE_INDEX_SQL)
        await self._conn.commit()
        logger.debug(f"[Storage] Connected to database: {path.resolve()}")

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    def _ensure_connected(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Storage not connected. Use `async with Storage(...):`.")
        return self._conn

    # -----------------------------------------------------------------------
    # Core Operations
    # -----------------------------------------------------------------------

    async def is_new(self, job_id: str) -> bool:
        """Returns True if this job ID has NOT been seen before."""
        conn = self._ensure_connected()
        async with conn.execute(IS_NEW_SQL, (job_id,)) as cursor:
            row = await cursor.fetchone()
        return row is None

    async def save_job(
        self,
        job: JobItem,
        score: int,
        reasons: list[str],
    ) -> bool:
        """
        Save a job to the database.
        Returns True if inserted, False if it already existed (OR IGNORE).
        """
        conn = self._ensure_connected()
        created_at = datetime.utcnow().isoformat()
        match_reasons_json = json.dumps(reasons, ensure_ascii=False)

        async with conn.execute(
            INSERT_JOB_SQL,
            (
                job.id,
                job.title,
                job.source,
                job.url,
                score,
                match_reasons_json,
                job.location,
                job.rate_or_hours,
                created_at,
            ),
        ) as cursor:
            inserted = cursor.rowcount > 0

        await conn.commit()

        if inserted:
            logger.debug(f"[Storage] Saved: '{job.title[:60]}' (score={score})")
        else:
            logger.debug(f"[Storage] Already exists: '{job.title[:60]}'")

        return inserted

    async def mark_notified(self, job_id: str) -> None:
        """Mark a job as successfully notified."""
        conn = self._ensure_connected()
        await conn.execute(MARK_NOTIFIED_SQL, (job_id,))
        await conn.commit()
        logger.debug(f"[Storage] Marked notified: {job_id}")

    # -----------------------------------------------------------------------
    # Utility
    # -----------------------------------------------------------------------

    async def get_stats(self) -> dict:
        """Return summary statistics about the database."""
        conn = self._ensure_connected()
        async with conn.execute(STATS_SQL) as cursor:
            row = await cursor.fetchone()
        if row:
            return {
                "total": row[0],
                "notified": row[1],
                "pending": row[2],
            }
        return {"total": 0, "notified": 0, "pending": 0}

    async def get_recent(self, limit: int = 10) -> list[dict]:
        """Return the most recently found jobs."""
        conn = self._ensure_connected()
        async with conn.execute(RECENT_JOBS_SQL, (limit,)) as cursor:
            rows = await cursor.fetchall()
        return [
            {
                "id": r[0],
                "title": r[1],
                "source": r[2],
                "url": r[3],
                "score": r[4],
                "match_reasons": json.loads(r[5]),
                "location": r[6],
                "rate_or_hours": r[7],
                "created_at": r[8],
                "notified": bool(r[9]),
            }
            for r in rows
        ]
