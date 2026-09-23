"""
WerkZoeker — Striive.com HTML Scraper

Scrapes the Striive platform (formerly Staffing MS / Striive)
for freelance/interim Detail Engineering assignments.
Handles pagination and rate limiting.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime
from urllib.parse import urljoin, urlencode

from bs4 import BeautifulSoup
from loguru import logger

from .base import BaseScraper, JobItem
from .freelancenl import FreelanceNLScraper

BASE_URL = "https://www.striive.com"
SEARCH_URL = f"{BASE_URL}/opdrachten"

# Search query sets to run
SEARCH_QUERIES = [
    "detail engineer elektrotechniek",
    "e-engineer hoogspanning",
    "eplan engineer",
    "werkvoorbereider elektrotechniek",
]


class StriiveScraper(BaseScraper):
    """
    HTML scraper for Striive.com freelance/interim assignments.
    Paginates through results up to MAX_PAGES.
    """

    SOURCE_NAME = "Striive.com"

    def __init__(self, max_pages: int = 5, **kwargs):
        super().__init__(**kwargs)
        self.max_pages = max_pages

    async def fetch_jobs(self) -> list[JobItem]:
        all_items: dict[str, JobItem] = {}

        for query in SEARCH_QUERIES:
            items = await self._fetch_all_pages(query)
            for item in items:
                if item.id not in all_items:
                    all_items[item.id] = item

        results = list(all_items.values())
        logger.info(f"[{self.SOURCE_NAME}] Found {len(results)} unique jobs")
        return results

    async def _fetch_all_pages(self, query: str) -> list[JobItem]:
        items: list[JobItem] = []

        for page in range(1, self.max_pages + 1):
            page_items = await self._fetch_page(query, page)
            if not page_items:
                logger.debug(
                    f"[{self.SOURCE_NAME}] No results on page {page} for '{query}', stopping"
                )
                break
            items.extend(page_items)
            logger.debug(
                f"[{self.SOURCE_NAME}] Page {page} for '{query}': {len(page_items)} jobs"
            )
            await asyncio.sleep(self.rate_limit_delay)

        return items

    async def _fetch_page(self, query: str, page: int) -> list[JobItem]:
        params = {
            "q": query,
            "page": page,
            "sort": "date",
        }
        url = f"{SEARCH_URL}?{urlencode(params)}"
        logger.debug(f"[{self.SOURCE_NAME}] GET {url}")

        response = await self.safe_get(url)
        if not response:
            return []

        return self._parse_page(response.text)

    def _parse_page(self, html: str) -> list[JobItem]:
        soup = BeautifulSoup(html, "lxml")
        items: list[JobItem] = []

        # Striive job cards — selectors may need updating if site changes
        # Try multiple selector patterns for resilience
        cards = (
            soup.select("article.assignment-card")
            or soup.select("div.job-card")
            or soup.select("div[class*='opdracht']")
            or soup.select("li.result-item")
            or soup.select("div.card--vacancy")
        )

        if not cards:
            logger.debug(f"[{self.SOURCE_NAME}] No job cards found in HTML (possible layout change)")
            return []

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
            or card.find(class_=lambda c: c and "title" in c.lower())
        )
        title = self.clean_text(title_el.get_text()) if title_el else ""

        # URL
        link_el = card.find("a", href=True)
        if not link_el:
            return None
        href = link_el["href"]
        url = href if href.startswith("http") else urljoin(BASE_URL, href)

        # Description
        desc_el = (
            card.find("p")
            or card.find(class_=lambda c: c and "description" in c.lower())
            or card.find(class_=lambda c: c and "summary" in c.lower())
        )
        description = self.clean_text(desc_el.get_text()) if desc_el else title

        # Location
        location = None
        loc_el = card.find(class_=lambda c: c and ("location" in c.lower() or "locatie" in c.lower()))
        if not loc_el:
            # Try common icon patterns
            for icon in card.find_all("span"):
                text = icon.get_text(strip=True)
                if any(city_hint in text for city_hint in ["Amsterdam", "Rotterdam", "Utrecht",
                                                            "Den Haag", "Eindhoven", "Groningen",
                                                            "Noord", "Zuid", "Oost", "West"]):
                    location = text
                    break
        else:
            location = self.clean_text(loc_el.get_text())

        # Rate / hours
        rate_or_hours = None
        for el in card.find_all(["span", "div", "p"]):
            text = el.get_text(strip=True)
            rate = FreelanceNLScraper._extract_rate(text)
            if rate:
                rate_or_hours = rate
                break

        # Date
        published_at = datetime.utcnow()
        date_el = card.find("time") or card.find(class_=lambda c: c and "date" in c.lower())
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
