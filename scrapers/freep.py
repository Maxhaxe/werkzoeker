"""
WerkZoeker — Freep.nl HTML Scraper

Freep is a Dutch freelance and interim broker specializing in project management,
engineering, IT, and public sector assignments.
"""

from __future__ import annotations

import asyncio

from bs4 import BeautifulSoup
from loguru import logger
from urllib.parse import urljoin

from .base import BaseScraper, JobItem

FREEP_URL = "https://freep.nl/opdrachten"


class FreepScraper(BaseScraper):
    """
    HTML Scraper for Freep.nl freelance assignments.
    """

    SOURCE_NAME = "Freep.nl"

    async def fetch_jobs(self) -> list[JobItem]:
        all_items: dict[str, JobItem] = {}

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }

        response = await self.safe_get(FREEP_URL, headers=headers)
        if response and response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if "/opdracht/" in href or "/opdrachten/" in href:
                    if href.rstrip("/") == "https://freep.nl/opdrachten" or href.strip("/") == "opdrachten":
                        continue
                    url = urljoin("https://freep.nl", href)
                    title = self.clean_text(a.get_text())
                    if not title or len(title) < 5 or title.lower() in ("opdrachten", "bekijk opdracht", "lees meer"):
                        continue

                    job_id = self.make_id(url)
                    if job_id not in all_items:
                        all_items[job_id] = JobItem(
                            id=job_id,
                            title=title,
                            source=self.SOURCE_NAME,
                            url=url,
                            description=f"{title} — Freelance / Interim opdracht bij Freep.nl",
                        )

        results = list(all_items.values())
        logger.info(f"[{self.SOURCE_NAME}] Found {len(results)} unique jobs")
        return results
