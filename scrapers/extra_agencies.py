"""
WerkZoeker — Extra Agencies (30 sources)

Generates 30 scrapers for top Dutch technical agencies and detachering companies.
Uses the Indeed RSS feed backend to extract vacancies specifically published
by these companies.
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
            # Bind the closure variable securely
            SOURCE_NAME = agency
            
            async def fetch_jobs(self) -> list[JobItem]:
                # Broaden the search slightly to ensure we capture all relevant jobs for this company
                queries = [
                    {"q": f'company:"{self.SOURCE_NAME}" detail engineer', "l": "Nederland"},
                    {"q": f'company:"{self.SOURCE_NAME}" e-engineer', "l": "Nederland"},
                    {"q": f'company:"{self.SOURCE_NAME}" eplan', "l": "Nederland"},
                    {"q": f'company:"{self.SOURCE_NAME}" elektrotechniek', "l": "Nederland"},
                    {"q": f'company:"{self.SOURCE_NAME}" hoogspanning', "l": "Nederland"},
                ]
                all_items = {}
                for params in queries:
                    items = await self._fetch_query(params)
                    for item in items:
                        # Ensure the source is correctly attributed to the agency, not Indeed
                        item.source = self.SOURCE_NAME
                        if item.id not in all_items:
                            all_items[item.id] = item
                    await asyncio.sleep(self.rate_limit_delay)
                return list(all_items.values())
                
        # Give the class a clean name for debugging/logging
        clean_name = agency.replace(" ", "").replace("&", "And").replace("-", "")
        AgencyScraper.__name__ = f"{clean_name}Scraper"
        scrapers.append(AgencyScraper)
        
    return scrapers

EXTRA_AGENCY_SCRAPERS = generate_agency_scrapers()
