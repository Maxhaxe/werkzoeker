"""
WerkZoeker — Yacht.nl HTML Scraper

Yacht is a top-tier Dutch recruitment and interim agency specializing in engineering,
IT, finance, and technical project consultancy.
"""

from __future__ import annotations

import asyncio

from bs4 import BeautifulSoup
from loguru import logger
from urllib.parse import urljoin

from .base import BaseScraper, JobItem
from .freelancenl import FreelanceNLScraper

YACHT_URLS = [
    "https://www.yacht.nl/vacatures/engineering",
    "https://www.yacht.nl/vacatures/ict",
]


class YachtScraper(BaseScraper):
    """
    HTML scraper for Yacht.nl — Engineering & Interim assignments.
    """

    SOURCE_NAME = "Yacht.nl"

    async def fetch_jobs(self) -> list[JobItem]:
        all_items: dict[str, JobItem] = {}

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }

        for target_url in YACHT_URLS:
            response = await self.safe_get(target_url, headers=headers)
            if not response or response.status_code != 200:
                continue

            soup = BeautifulSoup(response.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if "/vacatures/" in href and len(href.split("/")) > 2:
                    url = urljoin("https://www.yacht.nl", href)
                    title = self.clean_text(a.get_text())
                    if not title or len(title) < 5 or title.lower() in ("vacatures", "bekijk alle vacatures", "engineering"):
                        continue

                    job_id = self.make_id(url)
                    if job_id not in all_items:
                        all_items[job_id] = JobItem(
                            id=job_id,
                            title=title,
                            source=self.SOURCE_NAME,
                            url=url,
                            description=f"{title} — Interim/Freelance vacature bij Yacht.nl",
                            rate_or_hours=FreelanceNLScraper._extract_rate(title),
                        )

            await asyncio.sleep(self.rate_limit_delay)

        results = list(all_items.values())
        logger.info(f"[{self.SOURCE_NAME}] Found {len(results)} unique jobs")
        return results
