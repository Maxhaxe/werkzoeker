"""
WerkZoeker — Synsel Techniek HTML Scraper

Synsel Tech is a premier Dutch engineering recruitment agency specializing in
automation, electrical engineering, service engineering, and installation.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from loguru import logger

from .base import BaseScraper, JobItem

SYNSEL_URLS = [
    "https://www.synsel.nl/vacatures",
    "https://www.synsel.nl/vacatures?specialismen=field-service-engineers",
]


class SynselScraper(BaseScraper):
    """
    HTML Scraper for Synsel Techniek — Electrical & Automation Engineering.
    """

    SOURCE_NAME = "Synsel Techniek"

    async def fetch_jobs(self) -> list[JobItem]:
        all_items: dict[str, JobItem] = {}

        for target_url in SYNSEL_URLS:
            response = await self.safe_get(target_url)
            if not response or response.status_code != 200:
                continue

            soup = BeautifulSoup(response.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if "/vacature/" in href:
                    url = urljoin("https://www.synsel.nl", href.split("#")[0])
                    title = self.clean_text(a.get_text())
                    if not title or len(title) < 5 or title.lower() in ("meer info", "direct solliciteren", "bekijk vacature"):
                        continue

                    job_id = self.make_id(url)
                    if job_id not in all_items:
                        all_items[job_id] = JobItem(
                            id=job_id,
                            title=title,
                            source=self.SOURCE_NAME,
                            url=url,
                            description=f"{title} — Elektrotechniek & Automatisering vacature bij Synsel",
                            published_at=datetime.utcnow(),
                        )

            await asyncio.sleep(self.rate_limit_delay)

        results = list(all_items.values())
        logger.info(f"[{self.SOURCE_NAME}] Found {len(results)} unique jobs")
        return results
