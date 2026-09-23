"""
WerkZoeker — Indeed NL RSS Scraper

Parses Indeed's public RSS search feeds for Dutch freelance/ZZP
Detail Engineering roles.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET
from urllib.parse import urlencode

from loguru import logger

from .base import BaseScraper, JobItem
from .freelancenl import FreelanceNLScraper  # reuse _extract_rate helper

# Indeed NL RSS endpoint
INDEED_RSS_BASE = "https://nl.indeed.com/rss"

# Search terms tuned for Dutch Detail Engineering freelance jobs
SEARCH_QUERIES = [
    {"q": "detail engineer elektrotechniek freelance", "l": "Nederland"},
    {"q": "e-engineer zzp interim", "l": "Nederland"},
    {"q": "eplan engineer opdrachtbasis", "l": "Nederland"},
    {"q": "werkvoorbereider elektrotechniek interim", "l": "Nederland"},
    {"q": "hoogspanning engineer zzp", "l": "Nederland"},
]


class IndeedRSSScraper(BaseScraper):
    """
    Scrapes job listings from Indeed NL via RSS feeds.
    Indeed provides a public RSS feed for search queries.
    """

    SOURCE_NAME = "Indeed NL"

    async def fetch_jobs(self) -> list[JobItem]:
        all_items: dict[str, JobItem] = {}

        for params in SEARCH_QUERIES:
            items = await self._fetch_query(params)
            for item in items:
                if item.id not in all_items:
                    all_items[item.id] = item
            await asyncio.sleep(self.rate_limit_delay)

        results = list(all_items.values())
        logger.info(f"[{self.SOURCE_NAME}] Found {len(results)} unique jobs")
        return results

    async def _fetch_query(self, params: dict) -> list[JobItem]:
        url = f"{INDEED_RSS_BASE}?{urlencode(params)}"
        logger.debug(f"[{self.SOURCE_NAME}] Fetching: {url}")

        response = await self.safe_get(url)
        if not response:
            return []

        try:
            return self._parse_rss(response.text)
        except ET.ParseError as e:
            logger.warning(f"[{self.SOURCE_NAME}] XML parse error: {e}")
            return []

    def _parse_rss(self, xml_text: str) -> list[JobItem]:
        items: list[JobItem] = []
        try:
            xml_text = xml_text.lstrip("\ufeff")
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            logger.warning(f"[{self.SOURCE_NAME}] Failed to parse XML: {e}")
            return []

        channel = root.find("channel")
        if channel is None:
            return []

        for entry in channel.findall("item"):
            item = self._parse_item(entry)
            if item:
                items.append(item)

        return items

    def _parse_item(self, entry: ET.Element) -> JobItem | None:
        title = (entry.findtext("title") or "").strip()
        url = (entry.findtext("link") or "").strip()
        description_raw = entry.findtext("description") or ""
        pubdate_raw = entry.findtext("pubDate") or ""

        # Indeed puts location in <indeed:city>, <indeed:state>, or description
        location = self._extract_location(entry)

        if not url or not title:
            return None

        # Strip HTML tags from description
        description = self._strip_html(description_raw)
        rate_or_hours = FreelanceNLScraper._extract_rate(description)

        published_at = datetime.utcnow()
        if pubdate_raw:
            try:
                published_at = parsedate_to_datetime(pubdate_raw).replace(tzinfo=None)
            except Exception:
                pass

        return JobItem(
            id=self.make_id(url),
            title=title,
            source=self.SOURCE_NAME,
            url=url,
            description=description,
            location=location,
            rate_or_hours=rate_or_hours,
            published_at=published_at,
        )

    @staticmethod
    def _extract_location(entry: ET.Element) -> str | None:
        # Indeed uses namespaced elements; try common variants
        for tag in [
            "{com/indeed}city",
            "city",
            "location",
        ]:
            loc = entry.findtext(tag)
            if loc:
                return loc.strip()
        return None

    @staticmethod
    def _strip_html(html: str) -> str:
        """Remove HTML tags and decode common entities."""
        import re, html as html_mod
        text = re.sub(r"<[^>]+>", " ", html)
        text = html_mod.unescape(text)
        return BaseScraper.clean_text(text)
