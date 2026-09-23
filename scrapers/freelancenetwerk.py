"""
WerkZoeker — Freelancenetwerk.nl HTML Scraper

Freelancenetwerk is an active Dutch portal for freelance project assignments.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from loguru import logger

from .base import BaseScraper, JobItem
from .freelancenl import FreelanceNLScraper

TARGET_URLS = [
    "https://www.freelancenetwerk.nl/opdrachten",
    "https://nl.prolinker.com/opdrachten",
]


class FreelancenetwerkScraper(BaseScraper):
    """
    HTML scraper for Freelancenetwerk.nl / Prolinker.com freelance assignments.
    """

    SOURCE_NAME = "Freelancenetwerk.nl"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def fetch_jobs(self) -> list[JobItem]:
        all_items: dict[str, JobItem] = {}

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        }

        for target_url in TARGET_URLS:
            response = await self.safe_get(target_url, headers=headers)
            if not response:
                continue

            soup = BeautifulSoup(response.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if "/opdracht/" in href or "/opdrachten/" in href:
                    if href in ("/opdrachten", "/voor-opdrachtgevers"):
                        continue
                    url = urljoin("https://www.freelancenetwerk.nl", href)
                    title = self.clean_text(a.get_text())
                    if not title or len(title) < 5 or title.lower() in ("bekijk opdrachten", "opdrachten", "plaatsen"):
                        continue

                    job_id = self.make_id(url)
                    if job_id not in all_items:
                        all_items[job_id] = JobItem(
                            id=job_id,
                            title=title,
                            source=self.SOURCE_NAME,
                            url=url,
                            description=f"{title} — Freelance opdracht via Freelancenetwerk.nl",
                            rate_or_hours=FreelanceNLScraper._extract_rate(title),
                            published_at=datetime.utcnow(),
                        )

            await asyncio.sleep(self.rate_limit_delay)

        results = list(all_items.values())
        logger.info(f"[{self.SOURCE_NAME}] Found {len(results)} unique jobs")
        return results
