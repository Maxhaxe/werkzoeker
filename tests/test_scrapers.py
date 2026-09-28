"""
Unit tests for scrapers
"""

import pytest
import httpx
from unittest.mock import AsyncMock, patch

from scrapers.base import BaseScraper, JobItem
from scrapers.indeed_rss import IndeedRSSScraper
from main import get_scrapers

def test_make_id_deterministic():
    url = "https://example.com/vacature/123"
    id1 = BaseScraper.make_id(url)
    id2 = BaseScraper.make_id(url)
    assert id1 == id2
    assert len(id1) == 32

def test_get_scrapers_count():
    scrapers = get_scrapers(max_pages=1, rate_limit=0.1, timeout=5.0)
    assert len(scrapers) >= 50  # 23 base + 30 extra agencies

def test_indeed_rss_parser():
    rss_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
      <channel>
        <title>Indeed RSS Test</title>
        <item>
          <title>Detail Engineer Elektrotechniek</title>
          <link>https://nl.indeed.com/viewjob?jk=12345</link>
          <description>&lt;p&gt;Gezocht: EPLAN Engineer ZZP uurtarief €85&lt;/p&gt;</description>
          <pubDate>Mon, 28 Sep 2026 12:00:00 GMT</pubDate>
        </item>
      </channel>
    </rss>
    """
    scraper = IndeedRSSScraper()
    jobs = scraper._parse_rss(rss_xml)
    assert len(jobs) == 1
    assert jobs[0].title == "Detail Engineer Elektrotechniek"
    assert "EPLAN Engineer ZZP" in jobs[0].description
    assert jobs[0].source == "Indeed NL"
