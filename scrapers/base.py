"""
WerkZoeker — Scraper Base Module
Defines the shared JobItem dataclass and BaseScraper abstract class.
All scrapers inherit from BaseScraper.
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import httpx
from loguru import logger


# ---------------------------------------------------------------------------
# Data Model
# ---------------------------------------------------------------------------

@dataclass
class JobItem:
    """Standardised job posting object produced by every scraper."""

    id: str                          # SHA-256 hash of the canonical URL
    title: str
    source: str                      # Human-readable platform name
    url: str
    description: str
    location: Optional[str] = None
    rate_or_hours: Optional[str] = None
    published_at: datetime = field(default_factory=datetime.utcnow)
    start_date_label: Optional[str] = None  # e.g. "per direct", "~Oktober 2026", "onbekend"

    def __repr__(self) -> str:
        return f"<JobItem [{self.source}] '{self.title[:60]}' @ {self.url}>"


# ---------------------------------------------------------------------------
# Base Scraper
# ---------------------------------------------------------------------------

class BaseScraper(ABC):
    """
    Abstract base class for all WerkZoeker scrapers.

    Subclasses must implement `fetch_jobs()` and set `SOURCE_NAME`.
    A shared httpx.AsyncClient with sensible defaults is provided.
    """

    SOURCE_NAME: str = "Unknown"

    # Common browser-like headers to reduce blocking probability
    DEFAULT_HEADERS: dict[str, str] = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "nl-NL,nl;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
    }

    def __init__(self, timeout: float = 30.0, rate_limit_delay: float = 2.0, max_pages: int = 50, **kwargs):
        self.timeout = timeout
        self.rate_limit_delay = rate_limit_delay
        self.max_pages = max_pages
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "BaseScraper":
        self._client = httpx.AsyncClient(
            headers=self.DEFAULT_HEADERS,
            timeout=self.timeout,
            follow_redirects=True,
            http2=True,
        )
        return self

    async def __aexit__(self, *args) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError(
                f"{self.__class__.__name__} must be used as an async context manager. "
                "Use `async with scraper:` syntax."
            )
        return self._client

    @abstractmethod
    async def fetch_jobs(self) -> list[JobItem]:
        """
        Fetch and return a list of JobItem objects from the source.
        Must be implemented by every subclass.
        """
        ...

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def make_id(url: str) -> str:
        """Generate a stable, unique ID from a URL (first 16 hex chars of SHA-256)."""
        return hashlib.sha256(url.strip().lower().encode()).hexdigest()[:32]

    @staticmethod
    def clean_text(text: str) -> str:
        """Strip excess whitespace and normalise linebreaks."""
        if not text:
            return ""
        lines = [line.strip() for line in text.splitlines()]
        return " ".join(line for line in lines if line)

    @staticmethod
    def snippet(text: str, max_chars: int = 280) -> str:
        """Return a short snippet from a long description."""
        cleaned = BaseScraper.clean_text(text)
        if len(cleaned) <= max_chars:
            return cleaned
        # Try to break at a sentence boundary
        cut = cleaned[:max_chars]
        last_dot = cut.rfind(".")
        if last_dot > max_chars // 2:
            return cut[: last_dot + 1]
        return cut.rstrip() + "…"

    async def safe_get(self, url: str, **kwargs) -> Optional[httpx.Response]:
        """GET with error handling. Returns None on failure."""
        try:
            response = await self.client.get(url, **kwargs)
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as e:
            logger.warning(
                f"[{self.SOURCE_NAME}] HTTP {e.response.status_code} for {url}"
            )
        except httpx.RequestError as e:
            if "SSL" in str(e) or "certificate" in str(e).lower() or "record layer" in str(e).lower():
                try:
                    async with httpx.AsyncClient(verify=False, headers=self.DEFAULT_HEADERS, timeout=self.timeout, follow_redirects=True) as fallback_client:
                        res = await fallback_client.get(url, **kwargs)
                        res.raise_for_status()
                        return res
                except Exception as fb_err:
                    logger.warning(f"[{self.SOURCE_NAME}] SSL fallback also failed for {url}: {fb_err}")
            else:
                logger.warning(f"[{self.SOURCE_NAME}] Request error for {url}: {e}")
        return None
