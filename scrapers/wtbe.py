"""
WerkZoeker — WtbE Engineering HTML Scraper

WtbE is a specialised Dutch engineering recruitment & project consultancy for mechanical,
electrical, civil engineering, and industrial automation.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from loguru import logger

from .base import BaseScraper, JobItem

WTBE_URLS = [
    "https://www.wtbe.nl/vacatures/",
    "https://www.wtbe.nl/vacatures/engineering/",
    "https://www.wtbe.nl/vacatures/maintenance/",
]


class WtbEScraper(BaseScraper):
    """
    HTML Scraper for WtbE Engineering — Electrical & Mechanical Engineering.
    """

    SOURCE_NAME = "WtbE Engineering"

    async def fetch_jobs(self) -> list[JobItem]:
        all_items: dict[str, JobItem] = {}

        for target_url in WTBE_URLS:
            response = await self.safe_get(target_url)
            if not response or response.status_code != 200:
                continue

            soup = BeautifulSoup(response.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if "/vacatures/" in href and href.rstrip("/") not in ("https://www.wtbe.nl/vacatures", "/vacatures"):
                    url = urljoin("https://www.wtbe.nl", href)
                    title = self.clean_text(a.get_text())
                    if not title or len(title) < 5 or any(k in title.lower() for k in ("bekijk alle", "vacatures per", "over wtbe")):
                        continue

                    job_id = self.make_id(url)
                    if job_id not in all_items:
                        all_items[job_id] = JobItem(
                            id=job_id,
                            title=title,
                            source=self.SOURCE_NAME,
                            url=url,
                            description=f"{title} — WtbE Engineering & Techniek vacature",
                            published_at=datetime.utcnow(),
                        )

            await asyncio.sleep(self.rate_limit_delay)

        results = list(all_items.values())
        logger.info(f"[{self.SOURCE_NAME}] Found {len(results)} unique jobs")
        return results
