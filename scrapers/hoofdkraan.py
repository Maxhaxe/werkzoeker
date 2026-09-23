"""
WerkZoeker — Hoofdkraan.nl HTML Scraper

Hoofdkraan is a major Dutch marketplace for freelance and ZZP assignments
across engineering, technical, ICT, and advisory domains.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from urllib.parse import urljoin, urlencode

from bs4 import BeautifulSoup
from loguru import logger

from .base import BaseScraper, JobItem
from .freelancenl import FreelanceNLScraper

BASE_URL = "https://www.hoofdkraan.nl"
SEARCH_URL = f"{BASE_URL}/opdrachten"

SEARCH_QUERIES = [
    "elektrotechniek",
    "engineer",
    "eplan",
    "hoogspanning",
    "werkvoorbereider",
]


class HoofdkraanScraper(BaseScraper):
    """
    HTML scraper for Hoofdkraan.nl — Dutch freelance assignment marketplace.
    """

    SOURCE_NAME = "Hoofdkraan.nl"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def fetch_jobs(self) -> list[JobItem]:
        all_items: dict[str, JobItem] = {}

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        }

        for query in SEARCH_QUERIES:
            params = {"query": query}
            url = f"{SEARCH_URL}?{urlencode(params)}"
            response = await self.safe_get(url, headers=headers)
            if not response:
                continue

            soup = BeautifulSoup(response.text, "html.parser")
            # Find job cards or links
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if "/opdracht/" in href and not href.endswith("/plaatsen"):
                    url_full = urljoin(BASE_URL, href)
                    title = self.clean_text(a.get_text())
                    if not title or len(title) < 5 or title.lower() in ("plaats een opdracht", "opdrachten"):
                        continue

                    job_id = self.make_id(url_full)
                    if job_id not in all_items:
                        all_items[job_id] = JobItem(
                            id=job_id,
                            title=title,
                            source=self.SOURCE_NAME,
                            url=url_full,
                            description=f"{title} — Freelance opdracht op Hoofdkraan.nl",
                            rate_or_hours=FreelanceNLScraper._extract_rate(title),
                            published_at=datetime.utcnow(),
                        )

            await asyncio.sleep(self.rate_limit_delay)

        results = list(all_items.values())
        logger.info(f"[{self.SOURCE_NAME}] Found {len(results)} unique jobs")
        return results
