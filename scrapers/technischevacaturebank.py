"""
WerkZoeker — TechnischeVacaturebank.nl HTML Scraper

TechnischeVacaturebank.nl is a large Dutch aggregator specialized in
technical job postings (engineering, installation, electrotechnics).
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from urllib.parse import urljoin, urlencode

from bs4 import BeautifulSoup
from loguru import logger

from .base import BaseScraper, JobItem
from .freelancenl import FreelanceNLScraper

SEARCH_URL = "https://www.technischevacaturebank.nl/vacatures/zoeken"

SEARCH_QUERIES = [
    "elektrotechniek",
    "engineer",
    "eplan",
    "hoogspanning",
    "werkvoorbereider",
]


class TechnischeVacaturebankScraper(BaseScraper):
    """
    HTML scraper for TechnischeVacaturebank.nl tech job postings.
    """

    SOURCE_NAME = "TechnischeVacaturebank.nl"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def fetch_jobs(self) -> list[JobItem]:
        all_items: dict[str, JobItem] = {}

        for query in SEARCH_QUERIES:
            params = {"zoekterm": query}
            url = f"{SEARCH_URL}?{urlencode(params)}"
            response = await self.safe_get(url)
            if not response:
                continue

            soup = BeautifulSoup(response.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                # Links like /vacatures/47816264/technical-manager
                if href.startswith("/vacatures/") and len(href.split("/")) >= 4:
                    url = urljoin("https://www.technischevacaturebank.nl", href)
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
                            description=f"{title} — Vacature op TechnischeVacaturebank.nl",
                            rate_or_hours=FreelanceNLScraper._extract_rate(title),
                            published_at=datetime.utcnow(),
                        )

            await asyncio.sleep(self.rate_limit_delay)

        results = list(all_items.values())
        logger.info(f"[{self.SOURCE_NAME}] Found {len(results)} unique jobs")
        return results
