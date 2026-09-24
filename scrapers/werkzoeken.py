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
    "engineer e-installaties",
    "e-engineer",
    "electrical engineer",
    "ontwerptechnicus",
    "modelleur",
    "projectengineer",
    "senior engineer",
    "werkvoorbereider elektrotechniek",
    "eplan",
    "autocad",
    "bim",
    "gebouwgebonden",
    "lichtberekeningen",
    "brandmeld",
    "gbs",
    "zzp elektrotechniek",
    "freelance engineer",
    "interim engineer",
]


class WerkzoekenScraper(BaseScraper):
    """
    High-speed concurrent HTML scraper for Werkzoeken.nl.
    """

    SOURCE_NAME = "Werkzoeken.nl"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def fetch_jobs(self) -> list[JobItem]:
        all_items: dict[str, JobItem] = {}

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }

        async def _fetch_query(query: str) -> dict[str, JobItem]:
            query_items: dict[str, JobItem] = {}
            for page in range(1, min(15, self.max_pages + 1)):
                params = {"q": query, "page": page}
                url = f"{SEARCH_URL}?{urlencode(params)}"
                response = await self.safe_get(url, headers=headers)
                if not response or response.status_code != 200:
                    break

                soup = BeautifulSoup(response.text, "html.parser")
                page_links_count = 0
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    if "/vacature/" in href:
                        full_url = urljoin("https://www.werkzoeken.nl", href)
                        title = self.clean_text(a.get_text())
                        if not title or len(title) < 5 or title.lower() in ("bekijk vacature", "vacatures", "solliciteer"):
                            continue

                        page_links_count += 1
                        job_id = self.make_id(full_url)
                        if job_id not in query_items:
                            query_items[job_id] = JobItem(
                                id=job_id,
                                title=title,
                                source=self.SOURCE_NAME,
                                url=full_url,
                                description=f"{title} — Vacature/opdracht bij Werkzoeken.nl",
                                rate_or_hours=FreelanceNLScraper._extract_rate(title),
                                published_at=datetime.utcnow(),
                            )

                if page_links_count == 0:
                    break
                await asyncio.sleep(self.rate_limit_delay)
            return query_items

        results_list = await asyncio.gather(*[_fetch_query(q) for q in SEARCH_QUERIES])
        for res in results_list:
            all_items.update(res)

        results = list(all_items.values())
        logger.info(f"[{self.SOURCE_NAME}] Found {len(results)} unique jobs")
        return results
