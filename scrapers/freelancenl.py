"""
WerkZoeker — Freelance.nl RSS Scraper

Parses the public RSS feed from Freelance.nl filtered on relevant
Detail Engineering / elektrotechniek search terms.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

from loguru import logger

from .base import BaseScraper, JobItem

# Search queries to run against Freelance.nl RSS
# Each produces a separate feed URL
SEARCH_QUERIES = [
    "detail engineer elektrotechniek",
    "e-engineer zzp",
    "elektrotechnisch engineer freelance",
    "werkvoorbereider elektrotechniek",
    "hoogspanning engineer",
    "middenspanning engineer",
    "eplan engineer",
]

RSS_BASE_URL = "https://www.freelance.nl/vacatures/rss/"


class FreelanceNLScraper(BaseScraper):
    """
    Scrapes job listings from Freelance.nl via its public RSS feed.
    Runs multiple search queries and deduplicates results by URL.
    """

    SOURCE_NAME = "Freelance.nl"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def fetch_jobs(self) -> list[JobItem]:
        all_items: dict[str, JobItem] = {}  # keyed by id to deduplicate

        for query in SEARCH_QUERIES:
            items = await self._fetch_query(query)
            for item in items:
                if item.id not in all_items:
                    all_items[item.id] = item
            # Polite delay between queries
            await asyncio.sleep(self.rate_limit_delay)

        results = list(all_items.values())
        logger.info(f"[{self.SOURCE_NAME}] Found {len(results)} unique jobs")
        return results

    async def _fetch_query(self, query: str) -> list[JobItem]:
        params = {
            "zoekterm": query,
            "contracttype": "freelance",  # filter to freelance only
        }
        url = RSS_BASE_URL

        logger.debug(f"[{self.SOURCE_NAME}] Fetching query: '{query}'")
        response = await self.safe_get(url, params=params)
        if not response:
            return []

        try:
            return self._parse_rss(response.text)
        except ET.ParseError as e:
            logger.warning(f"[{self.SOURCE_NAME}] XML parse error for '{query}': {e}")
            return []

    def _parse_rss(self, xml_text: str) -> list[JobItem]:
        items: list[JobItem] = []

        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            # Try to recover by stripping BOM or encoding declarations
            xml_text = xml_text.lstrip("\ufeff")
            root = ET.fromstring(xml_text)

        # Handle both <rss><channel><item> and Atom feeds
        channel = root.find("channel")
        if channel is None:
            # Try Atom namespace
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            entries = root.findall("atom:entry", ns)
            return self._parse_atom_entries(entries, ns)

        for entry in channel.findall("item"):
            item = self._parse_rss_item(entry)
            if item:
                items.append(item)

        return items

    def _parse_rss_item(self, entry: ET.Element) -> JobItem | None:
        title_el = entry.find("title")
        link_el = entry.find("link")
        desc_el = entry.find("description")
        pubdate_el = entry.find("pubDate")
        location_el = entry.find("location")  # may not exist

        if title_el is None or link_el is None:
            return None

        title = (title_el.text or "").strip()
        url = (link_el.text or "").strip()
        description = self.clean_text(desc_el.text or "") if desc_el is not None else ""
        location = (location_el.text or "").strip() if location_el is not None else None

        published_at = datetime.utcnow()
        if pubdate_el is not None and pubdate_el.text:
            try:
                published_at = parsedate_to_datetime(pubdate_el.text).replace(tzinfo=None)
            except Exception:
                pass

        if not url:
            return None

        # Extract tarief/uren hints from description
        rate_or_hours = self._extract_rate(description)

        return JobItem(
            id=self.make_id(url),
            title=title,
            source=self.SOURCE_NAME,
            url=url,
            description=description,
            location=location or None,
            rate_or_hours=rate_or_hours,
            published_at=published_at,
        )

    def _parse_atom_entries(self, entries, ns: dict) -> list[JobItem]:
        items = []
        for entry in entries:
            title = entry.findtext("atom:title", namespaces=ns, default="").strip()
            link_el = entry.find("atom:link", ns)
            url = (link_el.get("href", "") if link_el is not None else "").strip()
            description = self.clean_text(
                entry.findtext("atom:summary", namespaces=ns, default="")
                or entry.findtext("atom:content", namespaces=ns, default="")
            )
            if not url:
                continue
            items.append(
                JobItem(
                    id=self.make_id(url),
                    title=title,
                    source=self.SOURCE_NAME,
                    url=url,
                    description=description,
                    published_at=datetime.utcnow(),
                )
            )
        return items

    @staticmethod
    def _extract_rate(text: str) -> str | None:
        """Try to extract a rate/hours indicator from description text."""
        import re
        # Match patterns like "€85/uur", "80-95 euro per uur", "40 uur per week"
        patterns = [
            r"€\s*\d+[\d,\.]*\s*[-–]\s*€?\s*\d+[\d,\.]*\s*/?\s*uur",
            r"€\s*\d+[\d,\.]*\s*/?\s*uur",
            r"\d+\s*[-–]\s*\d+\s*euro[^\w]",
            r"\d+\s*uur\s*per\s*week",
            r"uurtarief[:\s]+€?\s*\d+",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(0).strip()
        return None
