"""
WerkZoeker — Matchd HTML Scraper

Matchd is a major Dutch broker/agency for government, ICT, engineering,
interim assignments, and freelance (ZZP) roles.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from loguru import logger

from .base import BaseScraper, JobItem

MATCHD_URLS = [
    "https://matchd.nl/vacatures/",
]


class MatchdScraper(BaseScraper):
    """
    HTML Scraper for Matchd — Interim & Freelance / Engineering Vacancies.
    """

    SOURCE_NAME = "Matchd"

    async def fetch_jobs(self) -> list[JobItem]:
        all_items: dict[str, JobItem] = {}

        for target_url in MATCHD_URLS:
            response = await self.safe_get(target_url)
            if not response or response.status_code != 200:
                continue

            soup = BeautifulSoup(response.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if "/vacatures/" in href and href.strip("/") != "vacatures":
                    url = urljoin("https://matchd.nl", href)
                    title = self.clean_text(a.get_text())
                    if not title or len(title) < 5 or title.lower() in ("vacatures", "bekijk vacature", "solliciteer"):
                        continue

                    job_id = self.make_id(url)
                    if job_id not in all_items:
                        all_items[job_id] = JobItem(
                            id=job_id,
                            title=title,
                            source=self.SOURCE_NAME,
                            url=url,
                            description=f"{title} — Matchd Interim / ZZP vacature",
                            published_at=datetime.utcnow(),
                        )

            await asyncio.sleep(self.rate_limit_delay)

        results = list(all_items.values())
        logger.info(f"[{self.SOURCE_NAME}] Found {len(results)} unique jobs")
        return results
