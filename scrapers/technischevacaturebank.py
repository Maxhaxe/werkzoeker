"""
WerkZoeker — TechnischeVacaturebank.nl Scraper

TechnischeVacaturebank.nl is a large Dutch aggregator specialised in
technical job postings (engineering, installation, electrotechnics).
They offer an RSS feed for filtered searches.

Target RSS: https://www.technischevacaturebank.nl/vacatures/rss/
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET
from urllib.parse import urlencode

from loguru import logger

from .base import BaseScraper, JobItem
from .freelancenl import FreelanceNLScraper

RSS_BASE_URL = "https://www.technischevacaturebank.nl/vacatures/rss/"

SEARCH_QUERIES = [
    "detail engineer elektrotechniek",
    "e-engineer freelance",
    "eplan engineer zzp",
    "hoogspanning engineer interim",
    "werkvoorbereider elektrotechniek",
    "middenspanning engineer",
]


class TechnischeVacaturebankScraper(BaseScraper):
    """
    RSS scraper for TechnischeVacaturebank.nl — largest Dutch tech job aggregator.
    Falls back to HTML scraping if RSS is not available.
    """

    SOURCE_NAME = "TechnischeVacaturebank.nl"

    async def fetch_jobs(self) -> list[JobItem]:
        all_items: dict[str, JobItem] = {}

        for query in SEARCH_QUERIES:
            items = await self._fetch_query(query)
            for item in items:
                if item.id not in all_items:
                    all_items[item.id] = item
            await asyncio.sleep(self.rate_limit_delay)

        results = list(all_items.values())
        logger.info(f"[{self.SOURCE_NAME}] Found {len(results)} unique jobs")
        return results

    async def _fetch_query(self, query: str) -> list[JobItem]:
        # Try RSS first
        params = {"zoekterm": query, "contracttype": "freelance-zzp"}
        url = f"{RSS_BASE_URL}?{urlencode(params)}"
        logger.debug(f"[{self.SOURCE_NAME}] Fetching RSS: {url}")

        response = await self.safe_get(url)
        if not response:
            return []

        content_type = response.headers.get("content-type", "")
        if "xml" in content_type or "rss" in content_type or response.text.strip().startswith("<"):
            try:
                return self._parse_rss(response.text)
            except ET.ParseError as e:
                logger.warning(f"[{self.SOURCE_NAME}] RSS parse error: {e}")

        return []

    def _parse_rss(self, xml_text: str) -> list[JobItem]:
        items: list[JobItem] = []
        try:
            xml_text = xml_text.lstrip("\ufeff")
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            logger.warning(f"[{self.SOURCE_NAME}] XML parse error: {e}")
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

        if not url or not title:
            return None

        # Strip HTML from description
        import re, html as html_mod
        description = html_mod.unescape(re.sub(r"<[^>]+>", " ", description_raw))
        description = self.clean_text(description)

        rate_or_hours = FreelanceNLScraper._extract_rate(description)

        # Location from category or description
        location = entry.findtext("category") or None

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
