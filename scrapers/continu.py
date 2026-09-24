"""
WerkZoeker — Continu Professionals HTML Scraper

Continu Professionals is a Dutch staffing & recruitment specialist in engineering,
construction, and electrical installation (Elektrotechniek).
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from loguru import logger

from .base import BaseScraper, JobItem

CONTINU_URLS = [
    "https://www.continu.nl/vacatures/elektrotechniek",
    "https://www.continu.nl/vacatures/installatietechniek",
    "https://www.continu.nl/vacatures",
]


class ContinuScraper(BaseScraper):
    """
    HTML Scraper for Continu Professionals — Engineering & Elektrotechniek.
    """

    SOURCE_NAME = "Continu Professionals"

    async def fetch_jobs(self) -> list[JobItem]:
        all_items: dict[str, JobItem] = {}

        for target_url in CONTINU_URLS:
            for page in range(1, max(2, self.max_pages // 2 + 1)):
                page_url = f"{target_url}?page={page}" if page > 1 else target_url
                response = await self.safe_get(page_url)
                if not response or response.status_code != 200:
                    break

                soup = BeautifulSoup(response.text, "html.parser")
                found = 0
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    if "/vacatures/" in href or "/vacature/" in href:
                        url = urljoin("https://www.continu.nl", href)
                        title = self.clean_text(a.get_text())
                        if not title or len(title) < 5 or title.lower() in ("vacatures", "bekijk vacature", "lees meer"):
                            continue

                        job_id = self.make_id(url)
                        if job_id not in all_items:
                            found += 1
                            all_items[job_id] = JobItem(
                                id=job_id,
                                title=title,
                                source=self.SOURCE_NAME,
                                url=url,
                                description=f"{title} — Engineering / Elektrotechniek vacature bij Continu Professionals",
                                published_at=datetime.utcnow(),
                            )

                if found == 0:
                    break
                await asyncio.sleep(self.rate_limit_delay)

        results = list(all_items.values())
        logger.info(f"[{self.SOURCE_NAME}] Found {len(results)} unique jobs")
        return results
