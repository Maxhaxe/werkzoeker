"""
WerkZoeker — Striive.com API Scraper

Fetches freelance/interim Detail Engineering and technical assignments
directly from the public Striive API endpoint (striive-cms.codebridge.nl/api/jobs).
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime
from urllib.parse import urljoin

from loguru import logger

from .base import BaseScraper, JobItem

API_URL = "https://striive-cms.codebridge.nl/api/jobs"


class StriiveScraper(BaseScraper):
    """
    High-volume JSON API scraper for Striive.com freelance assignments.
    """

    SOURCE_NAME = "Striive.com"

    def __init__(self, max_pages: int = 20, **kwargs):
        super().__init__(**kwargs)
        self.max_pages = max_pages

    async def fetch_jobs(self) -> list[JobItem]:
        all_items: dict[str, JobItem] = {}

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json",
        }

        # Fetch pages up to max_pages (50 jobs per page)
        for page in range(1, self.max_pages + 1):
            url = f"{API_URL}?limit=50&page={page}"
            response = await self.safe_get(url, headers=headers)
            if not response or response.status_code != 200:
                break

            try:
                data = response.json()
            except Exception:
                break

            job_list = data.get("data", [])
            if not job_list:
                break

            for raw in job_list:
                title = self.clean_text(raw.get("title", ""))
                slug = raw.get("titleSlug", "")
                raw_id = raw.get("id", "")
                if not title or not raw_id:
                    continue

                url = f"https://www.striive.com/opdracht/{slug}-{raw_id}" if slug else f"https://www.striive.com/opdrachten/{raw_id}"
                job_id = self.make_id(url)

                if job_id in all_items:
                    continue

                # Location & Rate info
                city = raw.get("workSiteCity") or raw.get("location") or ""
                rate_min = raw.get("hourlyRateMin")
                rate_max = raw.get("hourlyRateMax")
                rate_str = None
                if rate_min and rate_max:
                    rate_str = f"€{rate_min}-€{rate_max}/uur"
                elif rate_min:
                    rate_str = f"€{rate_min}/uur"

                # Description / Content
                content = raw.get("content") or title
                clean_desc = self.clean_text(content)

                # Published date
                pub_date = datetime.utcnow()
                created_at = raw.get("publishedDate") or raw.get("createdAt")
                if created_at:
                    try:
                        from dateutil import parser as dateutil_parser
                        pub_date = dateutil_parser.parse(created_at).replace(tzinfo=None)
                    except Exception:
                        pass

                all_items[job_id] = JobItem(
                    id=job_id,
                    title=title,
                    source=self.SOURCE_NAME,
                    url=url,
                    description=clean_desc,
                    location=city if city else None,
                    rate_or_hours=rate_str,
                    published_at=pub_date,
                )

            await asyncio.sleep(self.rate_limit_delay)

        results = list(all_items.values())
        logger.info(f"[{self.SOURCE_NAME}] Found {len(results)} unique jobs via API")
        return results
