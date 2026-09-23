"""
WerkZoeker — BlueBeaver.nl HTML Scraper

BlueBeaver is an active Dutch ZZP platform for technical assignments with
up-to-date listings across engineering, electrical, and energy sectors.
"""

from __future__ import annotations

from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from loguru import logger

from .base import BaseScraper, JobItem
from .freelancenl import FreelanceNLScraper

BLUEBEAVER_CATEGORY_URLS = [
    "https://www.bluebeaver.nl/zzp-opdrachten-elektrotechniek",
    "https://www.bluebeaver.nl/zzp-opdrachten-energietechniek",
    "https://www.bluebeaver.nl/opdrachten-zzp",
]


class BlueBeaverScraper(BaseScraper):
    """
    HTML scraper for BlueBeaver.nl technical ZZP/freelance assignments.
    """

    SOURCE_NAME = "BlueBeaver.nl"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def fetch_jobs(self) -> list[JobItem]:
        all_items: dict[str, JobItem] = {}

        for target_url in BLUEBEAVER_CATEGORY_URLS:
            response = await self.safe_get(target_url)
            if not response:
                continue

            soup = BeautifulSoup(response.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if "/opdrachten/opdracht-" in href:
                    url = href if href.startswith("http") else urljoin("https://www.bluebeaver.nl", href)
                    title = self.clean_text(a.get_text())
                    if not title or len(title) < 5:
                        continue

                    job_id = self.make_id(url)
                    if job_id not in all_items:
                        all_items[job_id] = JobItem(
                            id=job_id,
                            title=title,
                            source=self.SOURCE_NAME,
                            url=url,
                            description=f"{title} — BlueBeaver ZZP opdracht Elektrotechniek / Energietechniek",
                            rate_or_hours=FreelanceNLScraper._extract_rate(title),
                            published_at=datetime.utcnow(),
                        )

        results = list(all_items.values())
        logger.info(f"[{self.SOURCE_NAME}] Found {len(results)} unique jobs")
        return results
