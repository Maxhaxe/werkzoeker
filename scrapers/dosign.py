"""
WerkZoeker — Dosign.nl HTML Scraper

Dosign is a specialist engineering staffing agency focusing
on energy, industry, utilities, and electrical engineering.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from loguru import logger

from .base import BaseScraper, JobItem
from .freelancenl import FreelanceNLScraper

DOSIGN_URLS = [
    "https://www.dosign.nl/discipline/elektrotechniek/vacatures",
    "https://www.dosign.nl/branche/utiliteitsbouw/vacatures",
    "https://www.dosign.nl/branche/duurzame-energie/vacatures",
    "https://www.dosign.nl/vacatures",
]


class DosignScraper(BaseScraper):
    """
    HTML scraper for Dosign.nl engineering & electrotechnics positions.
    """

    SOURCE_NAME = "Dosign.nl"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def fetch_jobs(self) -> list[JobItem]:
        all_items: dict[str, JobItem] = {}

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }

        for target_url in DOSIGN_URLS:
            response = await self.safe_get(target_url, headers=headers)
            if not response:
                continue

            soup = BeautifulSoup(response.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                # Match links like /vacatures/medior-engineer-elektrotechniek.../a0wP400...
                if "/vacatures/" in href and not href.endswith("/solliciteren") and href != "/vacatures":
                    url = urljoin("https://www.dosign.nl", href)
                    title = self.clean_text(a.get_text())
                    if not title or len(title) < 5 or title.lower() in ("lees meer", "bekijk vacature", "vacatures", "direct solliciteren"):
                        continue

                    job_id = self.make_id(url)
                    if job_id not in all_items:
                        all_items[job_id] = JobItem(
                            id=job_id,
                            title=title,
                            source=self.SOURCE_NAME,
                            url=url,
                            description=f"{title} — Engineering opdracht bij Dosign.nl",
                            rate_or_hours=FreelanceNLScraper._extract_rate(title),
                            published_at=datetime.utcnow(),
                        )

            await asyncio.sleep(self.rate_limit_delay)

        results = list(all_items.values())
        logger.info(f"[{self.SOURCE_NAME}] Found {len(results)} unique jobs")
        return results
