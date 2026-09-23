"""
WerkZoeker — VNOM.nl HTML Scraper

VNOM is a Dutch staffing network specialised in electrical installation
and engineering (elektrotechniek & installatietechniek).
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from loguru import logger

from .base import BaseScraper, JobItem
from .freelancenl import FreelanceNLScraper

VNOM_URLS = [
    "https://www.vnom.nl/vacatures/e-en-i-vacatures/",
    "https://www.vnom.nl/zzp-opdrachten",
    "https://www.vnom.nl/vacatures/elektro-en-installatietechniek",
    "https://www.vnom.nl/vacatures",
]


class VNOMScraper(BaseScraper):
    """
    HTML scraper for VNOM.nl — electrotechnics & installation engineering.
    """

    SOURCE_NAME = "VNOM.nl"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def fetch_jobs(self) -> list[JobItem]:
        all_items: dict[str, JobItem] = {}

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }

        for target_url in VNOM_URLS:
            response = await self.safe_get(target_url, headers=headers)
            if not response:
                continue

            soup = BeautifulSoup(response.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                # Match /vacatures/elektromonteur-vacatures or /vacatures/...
                if href.startswith("/vacatures/") or href.startswith("/zzp-opdrachten"):
                    if href in ("/vacatures/", "/zzp-opdrachten/"):
                        continue
                    url = urljoin("https://www.vnom.nl", href)
                    title = self.clean_text(a.get_text())
                    if not title or len(title) < 4 or title.lower() in ("bekijk vacatures", "bekijk vacature", "vacatures", "alle vacatures"):
                        continue

                    job_id = self.make_id(url)
                    if job_id not in all_items:
                        all_items[job_id] = JobItem(
                            id=job_id,
                            title=title,
                            source=self.SOURCE_NAME,
                            url=url,
                            description=f"{title} — Elektrotechniek vacature/opdracht bij VNOM.nl",
                            rate_or_hours=FreelanceNLScraper._extract_rate(title),
                            published_at=datetime.utcnow(),
                        )

            await asyncio.sleep(self.rate_limit_delay)

        results = list(all_items.values())
        logger.info(f"[{self.SOURCE_NAME}] Found {len(results)} unique jobs")
        return results
