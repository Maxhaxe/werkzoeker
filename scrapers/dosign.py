"""
WerkZoeker — Dosign.nl HTML Scraper

Dosign is a specialist engineering & R&D staffing agency with a strong focus
on energy, industry and utilities — including Detail Engineering, EPLAN,
AutoCAD, and high/medium voltage projects.

Target: https://www.dosign.nl/opdrachten
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from urllib.parse import urljoin, urlencode

from bs4 import BeautifulSoup
from loguru import logger

from .base import BaseScraper, JobItem
from .freelancenl import FreelanceNLScraper

BASE_URL = "https://www.dosign.nl"
SEARCH_URL = f"{BASE_URL}/opdrachten"

SEARCH_QUERIES = [
    "detail engineer",
    "elektrotechniek",
    "e-engineer",
    "eplan",
    "hoogspanning",
]


class DosignScraper(BaseScraper):
    """
    HTML scraper for Dosign.nl engineering/R&D freelance assignments.
    """

    SOURCE_NAME = "Dosign.nl"

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
            await asyncio.sleep(self.rate_limit_delay)

        results = list(all_items.values())
        logger.info(f"[{self.SOURCE_NAME}] Found {len(results)} unique jobs")
        return results

    async def _fetch_all_pages(self, query: str) -> list[JobItem]:
        items: list[JobItem] = []
        for page in range(1, self.max_pages + 1):
            params = {"q": query, "page": page}
            url = f"{SEARCH_URL}?{urlencode(params)}"
            logger.debug(f"[{self.SOURCE_NAME}] GET {url}")

            response = await self.safe_get(url)
            if not response:
                break

            page_items = self._parse_page(response.text)
            if not page_items:
                break

            items.extend(page_items)
            logger.debug(f"[{self.SOURCE_NAME}] Page {page} for '{query}': {len(page_items)} jobs")
            await asyncio.sleep(self.rate_limit_delay)

        return items

    def _parse_page(self, html: str) -> list[JobItem]:
        soup = BeautifulSoup(html, "lxml")

        # Try multiple selector patterns for Dosign's card layout
        cards = (
            soup.select("article.vacancy")
            or soup.select("div.vacancy-item")
            or soup.select("div.opdracht-item")
            or soup.select("li.vacancy")
            or soup.select("div[class*='vacancy']")
            or soup.select("div[class*='job']")
        )

        items = []
        for card in cards:
            item = self._parse_card(card)
            if item:
                items.append(item)
        return items

    def _parse_card(self, card) -> JobItem | None:
        title_el = (
            card.find("h2") or card.find("h3")
            or card.find(class_=lambda c: c and "title" in c.lower())
        )
        if not title_el:
            return None
        title = self.clean_text(title_el.get_text())

        link_el = title_el.find("a", href=True) or card.find("a", href=True)
        if not link_el:
            return None
        href = link_el["href"]
        url = href if href.startswith("http") else urljoin(BASE_URL, href)

        desc_el = card.find("p") or card.find(class_=lambda c: c and "description" in c.lower())
        description = self.clean_text(desc_el.get_text()) if desc_el else title

        location = None
        for el in card.find_all(["span", "div"]):
            cls = " ".join(el.get("class", []))
            if any(k in cls.lower() for k in ("location", "locatie", "place", "city")):
                location = self.clean_text(el.get_text())
                break

        rate_or_hours = FreelanceNLScraper._extract_rate(card.get_text(" ", strip=True))

        published_at = datetime.utcnow()
        date_el = card.find("time")
        if date_el:
            try:
                from dateutil import parser as dp
                published_at = dp.parse(
                    date_el.get("datetime") or date_el.get_text(strip=True),
                    dayfirst=True
                ).replace(tzinfo=None)
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
