"""
WerkZoeker — Tempo-Team Techniek HTML Scraper

Tempo-Team Techniek is a major technical recruitment platform in NL
covering electrical installation, mechanics, and technical operations.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from loguru import logger

from .base import BaseScraper, JobItem

TEMPOTEAM_URLS = [
    "https://www.tempo-team.nl/vacatures/techniek",
]


class TempoTeamScraper(BaseScraper):
    """
    HTML Scraper for Tempo-Team Techniek.
    """

    SOURCE_NAME = "Tempo-Team Techniek"

    async def fetch_jobs(self) -> list[JobItem]:
        all_items: dict[str, JobItem] = {}

        for target_url in TEMPOTEAM_URLS:
            response = await self.safe_get(target_url)
            if not response or response.status_code != 200:
                continue

            soup = BeautifulSoup(response.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if "/vacatures/" in href and href.strip("/") != "vacatures":
                    url = urljoin("https://www.tempo-team.nl", href)
                    title = self.clean_text(a.get_text())
                    if not title or len(title) < 5 or any(k in title.lower() for k in ("per regio", "bekijk alle", "vacatures per")):
                        continue

                    job_id = self.make_id(url)
                    if job_id not in all_items:
                        all_items[job_id] = JobItem(
                            id=job_id,
                            title=title,
                            source=self.SOURCE_NAME,
                            url=url,
                            description=f"{title} — Techniek vacature bij Tempo-Team",
                            published_at=datetime.utcnow(),
                        )

            await asyncio.sleep(self.rate_limit_delay)

        results = list(all_items.values())
        logger.info(f"[{self.SOURCE_NAME}] Found {len(results)} unique jobs")
        return results
