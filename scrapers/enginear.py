"""
WerkZoeker — Enginear.nl HTML Scraper

Enginear is a Dutch engineering consultancy specializing in electrical engineering,
civil engineering, and technical project management.
"""

from __future__ import annotations

import asyncio

from bs4 import BeautifulSoup
from loguru import logger
from urllib.parse import urljoin

from .base import BaseScraper, JobItem

ENGINEAR_URL = "https://enginear.nl/vacatures/"


class EnginearScraper(BaseScraper):
    """
    HTML Scraper for Enginear.nl.
    """

    SOURCE_NAME = "Enginear.nl"

    async def fetch_jobs(self) -> list[JobItem]:
        all_items: dict[str, JobItem] = {}

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }

        response = await self.safe_get(ENGINEAR_URL, headers=headers)
        if response and response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if "/vacatures/vacature-" in href or "/vacatures/" in href:
                    if href.rstrip("/") == "https://enginear.nl/vacatures" or href.strip("/") == "vacatures":
                        continue
                    url = urljoin("https://enginear.nl", href)
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
                            description=f"{title} — Engineering vacature bij Enginear",
                        )

        results = list(all_items.values())
        logger.info(f"[{self.SOURCE_NAME}] Found {len(results)} unique jobs")
        return results
