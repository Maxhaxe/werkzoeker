"""
WerkZoeker — Covebo Techniek HTML Scraper

Covebo is a Dutch technical staffing company providing jobs in installation,
electrical work, mechanics, and industrial technique.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from loguru import logger

from .base import BaseScraper, JobItem

COVEBO_URLS = [
    "https://www.covebo.nl/vacatures/techniek/",
    "https://www.covebo.nl/vacatures/",
]


class CoveboScraper(BaseScraper):
    """
    HTML Scraper for Covebo Techniek.
    """

    SOURCE_NAME = "Covebo Techniek"

    async def fetch_jobs(self) -> list[JobItem]:
        all_items: dict[str, JobItem] = {}

        for target_url in COVEBO_URLS:
            response = await self.safe_get(target_url)
            if not response or response.status_code != 200:
                continue

            soup = BeautifulSoup(response.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if "/vacature/" in href or "/vacatures/" in href:
                    if href.rstrip("/") in ("/vacatures", "/vacatures/techniek"):
                        continue
                    url = urljoin("https://www.covebo.nl", href)
                    title = self.clean_text(a.get_text())
                    if not title or len(title) < 5 or title.lower() in ("bekijk vacature", "solliciteer direct", "bekijk"):
                        continue

                    job_id = self.make_id(url)
                    if job_id not in all_items:
                        all_items[job_id] = JobItem(
                            id=job_id,
                            title=title,
                            source=self.SOURCE_NAME,
                            url=url,
                            description=f"{title} — Techniek vacature bij Covebo",
                            published_at=datetime.utcnow(),
                        )

            await asyncio.sleep(self.rate_limit_delay)

        results = list(all_items.values())
        logger.info(f"[{self.SOURCE_NAME}] Found {len(results)} unique jobs")
        return results
