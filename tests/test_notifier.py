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


def test_telegram_chat_ids_property():
    notifier = TelegramNotifier(bot_token="test_token", chat_id=" 12345, 67890 , -100999 ")
    assert notifier.chat_ids == ["12345", "67890", "-100999"]


@pytest.mark.asyncio
async def test_telegram_send_raw():
    notifier = TelegramNotifier(bot_token="test_token", chat_id="12345,67890")
    notifier._send_with_retry = AsyncMock()

    await notifier.send_raw("<b>Hello</b>", parse_mode="HTML", override_chat_id="999")
    notifier._send_with_retry.assert_called_once_with(
        "system",
        "<b>Hello</b>",
        parse_mode="HTML",
        override_chat_id="999",
    )


@pytest.mark.asyncio
async def test_notifier_dispatcher_send_raw_and_notifiers():
    dispatcher = NotifierDispatcher(chat_id="12345")
    assert len(dispatcher._notifiers) == 1
    assert isinstance(dispatcher._notifiers[0], TelegramNotifier)

    dispatcher._notifier.send_raw = AsyncMock()
    await dispatcher.send_raw("<b>Hello</b>", parse_mode="HTML")
    dispatcher._notifier.send_raw.assert_called_once_with(
        "<b>Hello</b>",
        parse_mode="HTML",
        override_chat_id=None,
    )


@pytest.mark.asyncio
async def test_send_daily_digest(monkeypatch):
    import main
    mock_jobs = [
        {
            "id": "job1",
            "title": "Electrical Engineer",
            "source": "Freelance.nl",
            "url": "https://example.com/job1",
            "location": "Utrecht",
            "rate_or_hours": "€85/u",
            "score": 10,
        }
    ]

    class MockStorage:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def get_jobs_last_24h(self):
            return mock_jobs

    monkeypatch.setattr(main, "Storage", MockStorage)

    mock_send_raw = AsyncMock()
    class MockDispatcher:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        send_raw = mock_send_raw

    monkeypatch.setattr(main, "NotifierDispatcher", MockDispatcher)

    await main.send_daily_digest()
    assert mock_send_raw.called
    call_args = mock_send_raw.call_args
    assert "Electrical Engineer" in call_args[0][0]
    assert call_args[1].get("parse_mode") == "HTML"


@pytest.mark.asyncio
async def test_pipeline_lock_busy():
    import main
    assert not main._pipeline_lock.locked()
    await main._pipeline_lock.acquire()
    try:
        stats = await main.run_pipeline()
        assert stats.get("status") == "busy"
    finally:
        main._pipeline_lock.release()


