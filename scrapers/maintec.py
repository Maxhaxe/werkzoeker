"""
WerkZoeker — Maintec HTML Scraper

Maintec is a Dutch technical agency specializing in electrical engineering,
installation, mechanical engineering, and technical recruitment.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from loguru import logger

from .base import BaseScraper, JobItem

MAINTEC_URLS = [
    "https://maintec.nl/vacatures/?keyword=Elektromonteur",
    "https://maintec.nl/vacatures/?keyword=Installateur",
    "https://maintec.nl/vacatures/?keyword=Elektrotechniek",
    "https://maintec.nl/vacatures/",
]


class MaintecScraper(BaseScraper):
    """
    HTML Scraper for Maintec — Technical & Electrical Jobs.
    """

    SOURCE_NAME = "Maintec"

    async def fetch_jobs(self) -> list[JobItem]:
        all_items: dict[str, JobItem] = {}

        for target_url in MAINTEC_URLS:
            response = await self.safe_get(target_url)
            if not response or response.status_code != 200:
                continue

            soup = BeautifulSoup(response.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if "/vacatures/vacature/" in href or ("~V-" in href and "/vacatures/" in href):
                    url = urljoin("https://maintec.nl", href)
                    title = self.clean_text(a.get_text())
                    if not title or len(title) < 5 or title.lower() in ("bekijk vacature", "solliciteer", "lees meer"):
                        continue

                    job_id = self.make_id(url)
                    if job_id not in all_items:
                        all_items[job_id] = JobItem(
                            id=job_id,
                            title=title,
                            source=self.SOURCE_NAME,
                            url=url,
                            description=f"{title} — Technische vacature bij Maintec",
                            published_at=datetime.utcnow(),
                        )

            await asyncio.sleep(self.rate_limit_delay)

        results = list(all_items.values())
        logger.info(f"[{self.SOURCE_NAME}] Found {len(results)} unique jobs")
        return results
