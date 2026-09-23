"""
WerkZoeker — Werkzoeken.nl HTML Scraper

Scrapes Werkzoeken.nl for freelance/interim Detail Engineering and electrotechnics assignments.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from urllib.parse import urljoin, urlencode

from bs4 import BeautifulSoup
from loguru import logger

from .base import BaseScraper, JobItem
from .freelancenl import FreelanceNLScraper

SEARCH_URL = "https://www.werkzoeken.nl/vacatures/"

SEARCH_QUERIES = [
    "elektrotechniek",
    "engineer",
    "eplan",
    "hoogspanning",
    "werkvoorbereider",
]


class WerkzoekenScraper(BaseScraper):
    """
    HTML scraper for Werkzoeken.nl.
    """

    SOURCE_NAME = "Werkzoeken.nl"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def fetch_jobs(self) -> list[JobItem]:
        all_items: dict[str, JobItem] = {}

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }

        for query in SEARCH_QUERIES:
            params = {"q": query}
            url = f"{SEARCH_URL}?{urlencode(params)}"
            response = await self.safe_get(url, headers=headers)
            if not response:
                continue

            soup = BeautifulSoup(response.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if "/vacature/" in href:
                    url = urljoin("https://www.werkzoeken.nl", href)
                    title = self.clean_text(a.get_text())
                    if not title or len(title) < 5 or title.lower() in ("bekijk vacature", "vacatures", "solliciteer"):
                        continue

                    job_id = self.make_id(url)
                    if job_id not in all_items:
                        all_items[job_id] = JobItem(
                            id=job_id,
                            title=title,
                            source=self.SOURCE_NAME,
                            url=url,
                            description=f"{title} — Vacature/opdracht bij Werkzoeken.nl",
                            rate_or_hours=FreelanceNLScraper._extract_rate(title),
                            published_at=datetime.utcnow(),
                        )

            await asyncio.sleep(self.rate_limit_delay)

        results = list(all_items.values())
        logger.info(f"[{self.SOURCE_NAME}] Found {len(results)} unique jobs")
        return results
