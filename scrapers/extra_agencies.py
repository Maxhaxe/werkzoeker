"""
WerkZoeker — Extra Agencies (30 sources)

Generates scrapers for top Dutch technical agencies and detachering companies.
Includes direct high-yield HTML scrapers for top platforms (Voort, Xelvin)
and feed-based scrapers for the remaining agencies.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from urllib.parse import urljoin
from typing import Type

from bs4 import BeautifulSoup
from loguru import logger

from .base import BaseScraper, JobItem
from .indeed_rss import IndeedRSSScraper


class VoortScraper(BaseScraper):
    """HTML Scraper for Voort Techniek & Detachering."""

    SOURCE_NAME = "Voort"

    async def fetch_jobs(self) -> list[JobItem]:
        all_items: dict[str, JobItem] = {}
        target_url = "https://www.voort.com/vacatures?vakgebied=techniek"

        response = await self.safe_get(target_url, headers=self.DEFAULT_HEADERS)
        if not response or response.status_code != 200:
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        try:
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if "/vacatures/" in href and len(href.rstrip("/").split("/")) >= 3:
                    url = urljoin("https://www.voort.com", href)
                    title = self.clean_text(a.get_text())
                    if not title or len(title) < 5 or any(k in title.lower() for k in ("vacatures", "bekijk", "lees meer", "solliciteer")):
                        continue

                    job_id = self.make_id(url)
                    if job_id not in all_items:
                        all_items[job_id] = JobItem(
                            id=job_id,
                            title=title,
                            source=self.SOURCE_NAME,
                            url=url,
                            description=f"{title} — Voort Techniek & Engineering vacature",
                            published_at=datetime.utcnow(),
                        )
        finally:
            soup.decompose()

        results = list(all_items.values())
        logger.info(f"[{self.SOURCE_NAME}] Found {len(results)} unique jobs")
        return results


class XelvinScraper(BaseScraper):
    """HTML Scraper for Xelvin Techniek & Engineering."""

    SOURCE_NAME = "Xelvin"

    async def fetch_jobs(self) -> list[JobItem]:
        all_items: dict[str, JobItem] = {}
        target_url = "https://www.xelvin.nl/vacatures"

        response = await self.safe_get(target_url, headers=self.DEFAULT_HEADERS)
        if not response or response.status_code != 200:
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        try:
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if "/vacatures/" in href and len(href.rstrip("/").split("/")) >= 3:
                    url = urljoin("https://www.xelvin.nl", href)
                    title = self.clean_text(a.get_text())
                    if not title or len(title) < 5 or any(k in title.lower() for k in ("vacatures", "bekijk", "lees meer", "solliciteer")):
                        continue

                    job_id = self.make_id(url)
                    if job_id not in all_items:
                        all_items[job_id] = JobItem(
                            id=job_id,
                            title=title,
                            source=self.SOURCE_NAME,
                            url=url,
                            description=f"{title} — Xelvin Techniek & Engineering vacature",
                            published_at=datetime.utcnow(),
                        )
        finally:
            soup.decompose()

        results = list(all_items.values())
        logger.info(f"[{self.SOURCE_NAME}] Found {len(results)} unique jobs")
        return results


AGENCIES = [
    "Brunel",
    "Maandag",
    "Krosto Techniek",
    "Polanski & Partners",
    "Kracht Recruitment",
    "YER",
    "Galjema",
    "Techsharks",
    "koen",
    "REEF",
    "TecPac",
    "Eminent",
    "Bowers",
    "Oranjegroep",
    "InAxtion",
    "Nouvall",
    "TTC",
    "Teqnion",
    "PDZ Uitzendbureau",
    "Profield",
    "Edison",
    "TechMatch",
    "Trinamics",
    "Forexx",
    "TMC",
    "Orion Engineering",
    "Moteq",
    "Tech-Consult",
]


def generate_agency_scrapers() -> list[Type[BaseScraper]]:
    """Create 30 scraper classes (Voort, Xelvin + 28 generated agencies)."""
    scrapers: list[Type[BaseScraper]] = [VoortScraper, XelvinScraper]

    for agency in AGENCIES:
        class AgencyScraper(IndeedRSSScraper):
            SOURCE_NAME = agency

            async def fetch_jobs(self) -> list[JobItem]:
                if IndeedRSSScraper._is_blocked:
                    return []
                params = {"q": f'"{self.SOURCE_NAME}" elektrotechniek OR engineering', "l": "Nederland"}
                items = await self._fetch_query(params)
                for item in items:
                    item.source = self.SOURCE_NAME
                return items

        clean_name = agency.replace(" ", "").replace("&", "And").replace("-", "")
        AgencyScraper.__name__ = f"{clean_name}Scraper"
        scrapers.append(AgencyScraper)

    return scrapers


EXTRA_AGENCY_SCRAPERS = generate_agency_scrapers()
