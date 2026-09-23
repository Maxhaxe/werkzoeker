"""
WerkZoeker — Randstad Techniek HTML Scraper

Randstad Techniek is one of the largest technical job portals in the Netherlands,
offering electrical engineering, installation, and technical job opportunities.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from loguru import logger

from .base import BaseScraper, JobItem

RANDSTAD_URLS = [
    "https://www.randstad.nl/vacatures/techniek",
    "https://www.randstad.nl/vacatures/techniek/elektrotechniek",
]


class RandstadTechniekScraper(BaseScraper):
    """
    HTML Scraper for Randstad Techniek.
    """

    SOURCE_NAME = "Randstad Techniek"

    async def fetch_jobs(self) -> list[JobItem]:
        all_items: dict[str, JobItem] = {}

        for target_url in RANDSTAD_URLS:
            response = await self.safe_get(target_url)
            if not response or response.status_code != 200:
                continue

            soup = BeautifulSoup(response.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if "/vacatures/" in href and href.strip("/") != "vacatures":
                    url = urljoin("https://www.randstad.nl", href)
                    title = self.clean_text(a.get_text())
                    if not title or len(title) < 5 or any(k in title.lower() for k in ("per stad", "bekijk alle", "vacatures per")):
                        continue

                    job_id = self.make_id(url)
                    if job_id not in all_items:
                        all_items[job_id] = JobItem(
                            id=job_id,
                            title=title,
                            source=self.SOURCE_NAME,
                            url=url,
                            description=f"{title} — Techniek vacature bij Randstad Techniek",
                            published_at=datetime.utcnow(),
                        )

            await asyncio.sleep(self.rate_limit_delay)

        results = list(all_items.values())
        logger.info(f"[{self.SOURCE_NAME}] Found {len(results)} unique jobs")
        return results
