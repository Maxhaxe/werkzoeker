"""
Unit tests for notifier.py
"""

import pytest
from scrapers.base import JobItem
from notifier import TelegramNotifier, NotifierDispatcher

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
