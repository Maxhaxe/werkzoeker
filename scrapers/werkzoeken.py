"""
WerkZoeker — Werkzoeken.nl HTML Scraper

Scrapes Werkzoeken.nl for freelance/interim Detail Engineering
assignments. Werkzoeken.nl aggregates listings from many Dutch job boards.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from urllib.parse import urljoin, urlencode

from bs4 import BeautifulSoup
from loguru import logger

from .base import BaseScraper, JobItem
from .freelancenl import FreelanceNLScraper

BASE_URL = "https://www.werkzoeken.nl"
SEARCH_URL = f"{BASE_URL}/vacatures"

SEARCH_QUERIES = [
    {"zoekwoord": "detail engineer elektrotechniek", "contractsoort": "freelance"},
    {"zoekwoord": "e-engineer zzp", "contractsoort": "freelance"},
    {"zoekwoord": "eplan hoogspanning interim"},
    {"zoekwoord": "werkvoorbereider elektrotechniek freelance"},
]


class WerkzoekenScraper(BaseScraper):
    """
    HTML scraper for Werkzoeken.nl — a Dutch job aggregator.
    Searches multiple queries and paginates results.
    """

    SOURCE_NAME = "Werkzoeken.nl"

    def __init__(self, max_pages: int = 5, **kwargs):
        super().__init__(**kwargs)
        self.max_pages = max_pages

    async def fetch_jobs(self) -> list[JobItem]:
        all_items: dict[str, JobItem] = {}

        for query_params in SEARCH_QUERIES:
            items = await self._fetch_all_pages(query_params)
            for item in items:
                if item.id not in all_items:
                    all_items[item.id] = item

        results = list(all_items.values())
        logger.info(f"[{self.SOURCE_NAME}] Found {len(results)} unique jobs")
        return results

    async def _fetch_all_pages(self, query_params: dict) -> list[JobItem]:
        items: list[JobItem] = []

        for page in range(1, self.max_pages + 1):
            params = {**query_params, "pagina": page}
            url = f"{SEARCH_URL}?{urlencode(params)}"
            logger.debug(f"[{self.SOURCE_NAME}] GET {url}")

            response = await self.safe_get(url)
            if not response:
                break

            page_items = self._parse_page(response.text)
            if not page_items:
                logger.debug(
                    f"[{self.SOURCE_NAME}] Empty page {page} for {query_params}, stopping"
                )
                break

            items.extend(page_items)
            logger.debug(f"[{self.SOURCE_NAME}] Page {page}: {len(page_items)} jobs")
            await asyncio.sleep(self.rate_limit_delay)

        return items

    def _parse_page(self, html: str) -> list[JobItem]:
        soup = BeautifulSoup(html, "lxml")
        items: list[JobItem] = []

        # Try multiple possible card selectors
        cards = (
            soup.select("article.vacature-card")
            or soup.select("div.vacature-item")
            or soup.select("li.search-result")
            or soup.select("div[class*='vacature']")
            or soup.select("div.job-result")
        )

        if not cards:
            logger.debug(f"[{self.SOURCE_NAME}] No cards found — checking for SERP-style results")
            # Werkzoeken sometimes uses a simple list format
            cards = soup.select("div.result") or soup.select("div.listing")

        for card in cards:
            item = self._parse_card(card)
            if item:
                items.append(item)

        return items

    def _parse_card(self, card) -> JobItem | None:
        # Title
        title_el = (
            card.find("h2")
            or card.find("h3")
            or card.find("h4")
            or card.find(class_=lambda c: c and "titel" in c.lower())
            or card.find(class_=lambda c: c and "title" in c.lower())
        )
        if not title_el:
            return None
        title = self.clean_text(title_el.get_text())

        # URL — prefer specific job links over generic ones
        link_el = title_el.find("a", href=True) or card.find("a", href=True)
        if not link_el:
            return None
        href = link_el["href"]
        url = href if href.startswith("http") else urljoin(BASE_URL, href)

        # Description
        desc_el = (
            card.find("p")
            or card.find(class_=lambda c: c and "omschrijving" in c.lower())
            or card.find(class_=lambda c: c and "description" in c.lower())
        )
        description = self.clean_text(desc_el.get_text()) if desc_el else title

        # Location
        location = None
        loc_candidates = card.find_all(class_=lambda c: c and (
            "locatie" in c.lower() or "location" in c.lower() or "plaats" in c.lower()
        ))
        if loc_candidates:
            location = self.clean_text(loc_candidates[0].get_text())

        # Rate / hours
        rate_or_hours = None
        full_text = card.get_text(" ", strip=True)
        rate_or_hours = FreelanceNLScraper._extract_rate(full_text)

        # Date
        published_at = datetime.utcnow()
        date_el = card.find("time")
        if date_el:
            dt_str = date_el.get("datetime") or date_el.get_text(strip=True)
            try:
                from dateutil import parser as dateutil_parser
                published_at = dateutil_parser.parse(dt_str, dayfirst=True).replace(tzinfo=None)
            except Exception:
                pass

        if not title or not url:
            return None

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
