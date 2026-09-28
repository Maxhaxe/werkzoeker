"""
Unit tests for storage.py
"""

import pytest
import pytest_asyncio
from storage import Storage
from scrapers.base import JobItem

@pytest.mark.asyncio
async def test_storage_lifecycle(temp_db_path, sample_valid_job):
    async with Storage(db_path=temp_db_path) as db:
        # Initial state
        is_new_before = await db.is_new(sample_valid_job.id)
        assert is_new_before is True

        # Save job
        await db.save_job(sample_valid_job, score=8, reasons=["eplan", "middenspanning"])

        # Deduplication check
        is_new_after = await db.is_new(sample_valid_job.id)
        assert is_new_after is False

        # Mark notified
        await db.mark_notified(sample_valid_job.id)

        # Stats check
        stats = await db.get_stats()
        assert stats["total"] == 1
        assert stats["notified"] == 1

        # 24h jobs check
        jobs_24h = await db.get_jobs_last_24h()
        assert len(jobs_24h) == 1
        assert jobs_24h[0]["title"] == sample_valid_job.title
