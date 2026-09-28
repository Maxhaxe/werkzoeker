"""
WerkZoeker — Extra Agencies (30 sources)

Generates 30 scrapers for top Dutch technical agencies and detachering companies.
Uses the Indeed RSS feed backend to extract vacancies published by these companies.
"""

from __future__ import annotations
import asyncio
from typing import Type

from .indeed_rss import IndeedRSSScraper
from .base import JobItem

AGENCIES = [
    "Brunel",
    "Maandag",
    "Xelvin",
    "Voort",
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

def generate_agency_scrapers() -> list[Type[IndeedRSSScraper]]:
    """Dynamically create 30 scraper classes targeting specific agencies."""
    scrapers = []
    
    for agency in AGENCIES:
        class AgencyScraper(IndeedRSSScraper):
            SOURCE_NAME = agency
            
            async def fetch_jobs(self) -> list[JobItem]:
                # 1 targeted query per agency to prevent rate-limiting (150 requests reduced to 30)
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
