"""
WerkZoeker — Technical Valley HTML Scraper

Technical Valley is a specialised Dutch recruiter and engineering partner
in energy transition, smart grid, electrical engineering, and installation.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from loguru import logger

from .base import BaseScraper, JobItem

TECHNICALVALLEY_URLS = [
    "https://technicalvalley.com/vacatures/",
]


class TechnicalValleyScraper(BaseScraper):
    """
    HTML Scraper for Technical Valley — Energy & Electrical Engineering.
    """

    SOURCE_NAME = "Technical Valley"

    async def fetch_jobs(self) -> list[JobItem]:
        all_items: dict[str, JobItem] = {}

        for target_url in TECHNICALVALLEY_URLS:
            response = await self.safe_get(target_url)
            if not response or response.status_code != 200:
                continue

            soup = BeautifulSoup(response.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if "/vacatures/" in href and href.strip("/") != "vacatures":
                    url = urljoin("https://technicalvalley.com", href)
                    title = self.clean_text(a.get_text())
                    if not title or len(title) < 5 or title.lower() in ("vacatures", "bekijk vacature", "lees meer"):
                        continue

                    job_id = self.make_id(url)
                    if job_id not in all_items:
                        all_items[job_id] = JobItem(
                            id=job_id,
                            title=title,
                            source=self.SOURCE_NAME,
                            url=url,
                            description=f"{title} — Energietechniek / Elektrotechniek vacature bij Technical Valley",
                            published_at=datetime.utcnow(),
                        )

            await asyncio.sleep(self.rate_limit_delay)

        results = list(all_items.values())
        logger.info(f"[{self.SOURCE_NAME}] Found {len(results)} unique jobs")
        return results
