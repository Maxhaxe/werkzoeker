"""
WerkZoeker — Freelance.nl HTML Scraper

Parses engineering, system integration, construction, and IT freelance assignments
from Freelance.nl.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from loguru import logger

from .base import BaseScraper, JobItem

FREELANCE_NL_CATEGORIES = [
    "https://www.freelance.nl/opdrachten/systeem-componentintegratie",
    "https://www.freelance.nl/opdrachten/constructie-fabricage-advies",
    "https://www.freelance.nl/opdrachten/constructie-fabricage-uitvoerend",
    "https://www.freelance.nl/opdrachten/ontwikkeling-implementatie",
    "https://www.freelance.nl/opdrachten/ict",
    "https://www.freelance.nl/opdrachten",
]


class FreelanceNLScraper(BaseScraper):
    """
    HTML scraper for Freelance.nl — largest Dutch freelance/ZZP assignment board.
    """

    SOURCE_NAME = "Freelance.nl"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def fetch_jobs(self) -> list[JobItem]:
        all_items: dict[str, JobItem] = {}

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

        for target_url in FREELANCE_NL_CATEGORIES:
            for page in range(1, self.max_pages + 1):
                page_url = f"{target_url}?page={page}" if page > 1 else target_url
                response = await self.safe_get(page_url, headers=headers)
                if not response or response.status_code != 200:
                    break

                soup = BeautifulSoup(response.text, "html.parser")
                page_links_count = 0
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    if "/opdracht/" in href or "/opdrachten/" in href:
                        if href.count("/") <= 2 or href.endswith("/opdrachten"):
                            continue
                        url = urljoin("https://www.freelance.nl", href)
                        title = self.clean_text(a.get_text())
                        if not title or len(title) < 5 or title.lower() in ("bekijk opdrachten", "opdrachten", "lees meer"):
                            continue

                        page_links_count += 1
                        job_id = self.make_id(url)
                        if job_id not in all_items:
                            all_items[job_id] = JobItem(
                                id=job_id,
                                title=title,
                                source=self.SOURCE_NAME,
                                url=url,
                                description=f"{title} — Freelance.nl ZZP opdracht",
                                rate_or_hours=self._extract_rate(title),
                                published_at=datetime.utcnow(),
                            )

                if page_links_count == 0:
                    break
                await asyncio.sleep(self.rate_limit_delay)

        results = list(all_items.values())
        logger.info(f"[{self.SOURCE_NAME}] Found {len(results)} unique jobs")
        return results

    @staticmethod
    def _extract_rate(text: str) -> str | None:
        """Try to extract a rate/hours indicator from text."""
        import re
        patterns = [
            r"€\s*\d+[\d,\.]*\s*[-–]\s*€?\s*\d+[\d,\.]*\s*/?\s*uur",
            r"€\s*\d+[\d,\.]*\s*/?\s*uur",
            r"\d+\s*[-–]\s*\d+\s*euro[^\w]",
            r"\d+\s*uur\s*per\s*week",
            r"uurtarief[:\s]+€?\s*\d+",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(0).strip()
        return None
