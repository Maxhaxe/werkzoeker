"""
Unit tests for notifier.py and command handler
"""

import pytest
import html
from unittest.mock import AsyncMock
from scrapers.base import JobItem
from notifier import TelegramNotifier, NotifierDispatcher
from bot_commands import TelegramCommandHandler

def test_telegram_format_message(sample_valid_job):
    notifier = TelegramNotifier(bot_token="test_token", chat_id="12345")
    formatted = notifier._format_message(
        sample_valid_job,
        score=10,
        reasons=["eplan pro panel", "middenspanning", "nen 1010"]
    )
    assert "Werkvoorbereider" in formatted
    assert "85" in formatted and "95" in formatted
    assert "eplan pro panel" in formatted
    assert "10" in formatted

def test_telegram_html_escaping():
    job = JobItem(
        id="job-html-test",
        title="Detail Engineer <EPLAN & AutoCAD>",
        source="Test & Portal",
        url="https://example.com/job?a=1&b=2",
        description="Text with <tags> & 'quotes'",
    )
    notifier = TelegramNotifier(bot_token="test_token", chat_id="12345")
    formatted = notifier._format_message(job, score=8, reasons=["eplan"])
    assert "Detail Engineer" in formatted
    assert "Test" in formatted

@pytest.mark.asyncio
async def test_cmd_run_html_escaping(sample_valid_job):
    async def mock_run_pipeline(override_chat_id=None):
        return {
            "scraped": 10,
            "passed_filter": 1,
            "new_jobs": 1,
            "notified": 1,
            "errors": 0,
            "passed_jobs": [(sample_valid_job, 8)]
        }

    handler = TelegramCommandHandler(run_pipeline_fn=mock_run_pipeline)
    handler._send = AsyncMock()
    handler._active_chat_id = "12345"

    await handler._cmd_run("")
    # Give async task time to run
    import asyncio
    await asyncio.sleep(0.1)

    assert handler._send.called
    sent_text = handler._send.call_args[0][0]
    assert "Scan voltooid" in sent_text
    assert html.escape(sample_valid_job.title) in sent_text
