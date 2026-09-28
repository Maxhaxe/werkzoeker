"""
WerkZoeker — Start Date & End Date Parser

Extracts assignment start date, end date, and deadline information from
Dutch (and English) job description text. Returns parsed dates and human labels.

Recognised patterns:
  - "per direct" / "z.s.m." / "zo snel mogelijk" → today
  - "per 1 oktober 2026" / "vanaf oktober 2026" → specific date/month
  - "Q1 2027" / "4e kwartaal 2026" → estimated quarter start
  - "over 3 maanden" → relative date
  - "einddatum 31-12-2026", "loopt tot 15 nov 2026" → end date
  - Nothing found → (None, "onbekend")
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Optional

# ---------------------------------------------------------------------------
# Month name → number mapping (Dutch + English)
# ---------------------------------------------------------------------------

MONTH_MAP: dict[str, int] = {
    # Dutch
    "januari": 1, "jan": 1,
    "februari": 2, "feb": 2,
    "maart": 3, "mrt": 3, "mar": 3,
    "april": 4, "apr": 4,
    "mei": 5,
    "juni": 6, "jun": 6,
    "juli": 7, "jul": 7,
    "augustus": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "oktober": 10, "okt": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
    # English
    "january": 1, "february": 2, "march": 3,
    "may": 5, "june": 6, "july": 7,
    "august": 8, "october": 10,
}

QUARTER_TO_MONTH: dict[int, int] = {1: 1, 2: 4, 3: 7, 4: 10}


# ---------------------------------------------------------------------------
# Helper: safe year extraction
# ---------------------------------------------------------------------------

def _resolve_year(raw_year: str | None) -> int:
    """Return explicit year if provided, else current or next year."""
    today = date.today()
    if raw_year:
        try:
            y = int(raw_year)
            if 2020 <= y <= 2035:
                return y
        except ValueError:
            pass
    return today.year if today.month <= 10 else today.year + 1


# ---------------------------------------------------------------------------
# Pattern matchers for Start Date
# ---------------------------------------------------------------------------

def _match_per_direct(text: str) -> Optional[tuple[date, str]]:
    patterns = [
        r"\bper\s+direct\b",
        r"\bz\.?\s*s\.?\s*m\.?\b",
        r"\bzo\s+snel\s+mogelijk\b",
        r"\bimmediately\b",
        r"\bimmediate\s+start\b",
        r"\bstart\s+asap\b",
        r"\bper\s+meteen\b",
    ]
    for p in patterns:
        if re.search(p, text, re.IGNORECASE):
            return date.today(), "per direct"
    return None


def _match_specific_date(text: str) -> Optional[tuple[date, str]]:
    """Match patterns like 'per 1 oktober 2026', 'vanaf 15 nov 2026', '01-10-2026'."""
    p1 = re.search(
        r"\b(?:per|vanaf|start(?:datum)?|ingang(?:sdatum)?)?\s*(\d{1,2})\s+("
        + "|".join(MONTH_MAP)
        + r")\s*(\d{4})?\b",
        text, re.IGNORECASE
    )
    if p1:
        day = int(p1.group(1))
        month = MONTH_MAP[p1.group(2).lower()]
        year = _resolve_year(p1.group(3))
        try:
            d = date(year, month, day)
            return d, f"{day} {p1.group(2).capitalize()} {year}"
        except ValueError:
            pass

    p2 = re.search(r"\b(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{4})\b", text)
    if p2:
        try:
            d = date(int(p2.group(3)), int(p2.group(2)), int(p2.group(1)))
            return d, d.strftime("%d-%m-%Y")
        except ValueError:
            pass

    return None


def _match_month_year(text: str) -> Optional[tuple[date, str]]:
    """Match 'oktober 2026', 'start in november 2026', 'vanaf maart 2027'."""
    p = re.search(
        r"\b(?:per|vanaf|start(?:datum)?|begin|in)\s+("
        + "|".join(MONTH_MAP)
        + r")\s+(\d{4})\b",
        text, re.IGNORECASE
    )
    if p:
        month = MONTH_MAP[p.group(1).lower()]
        year = int(p.group(2))
        try:
            d = date(year, month, 1)
            label = f"~{p.group(1).capitalize()} {year}"
            return d, label
        except ValueError:
            pass
    return None


def _match_quarter(text: str) -> Optional[tuple[date, str]]:
    """Match 'Q3 2026', '3e kwartaal 2026'."""
    word_to_q = {
        "eerste": 1, "1e": 1, "eerste kwartaal": 1,
        "tweede": 2, "2e": 2, "tweede kwartaal": 2,
        "derde": 3, "3e": 3, "derde kwartaal": 3,
        "vierde": 4, "4e": 4, "vierde kwartaal": 4,
    }
    p1 = re.search(r"\bQ([1-4])\s*(\d{4})?\b", text, re.IGNORECASE)
    if p1:
        q = int(p1.group(1))
        year = _resolve_year(p1.group(2))
        month = QUARTER_TO_MONTH[q]
        d = date(year, month, 1)
        return d, f"Q{q} {year}"

    p2 = re.search(
        r"\b([1-4]e|eerste|tweede|derde|vierde)\s+kwartaal\s*(\d{4})?\b",
        text, re.IGNORECASE
    )
    if p2:
        raw = p2.group(1).lower()
        q = word_to_q.get(raw) or word_to_q.get(raw + " kwartaal")
        if q:
            year = _resolve_year(p2.group(2))
            month = QUARTER_TO_MONTH[q]
            d = date(year, month, 1)
            return d, f"Q{q} {year}"

    return None


def _match_relative(text: str) -> Optional[tuple[date, str]]:
    """Match 'over 3 maanden', 'binnen 6 weken'."""
    p = re.search(
        r"\b(?:over|binnen|in)\s+(\d+)\s+(week(?:en)?|maand(?:en)?)\b",
        text, re.IGNORECASE
    )
    if p:
        n = int(p.group(1))
        unit = p.group(2).lower()
        today = date.today()
        if "week" in unit:
            d = today + timedelta(weeks=n)
            label = f"over ~{n} weken"
        else:
            d = today + timedelta(days=n * 30)
            label = f"over ~{n} maanden"
        return d, label
    return None


def _match_begin_half_end(text: str) -> Optional[tuple[date, str]]:
    """Match 'begin oktober 2026', 'half november 2026'."""
    p = re.search(
        r"\b(begin|half|midden)\s+(" + "|".join(MONTH_MAP) + r")\s*(\d{4})?\b",
        text, re.IGNORECASE
    )
    if p:
        position = p.group(1).lower()
        month = MONTH_MAP[p.group(2).lower()]
        year = _resolve_year(p.group(3))
        day = 1 if "begin" in position else 15
        try:
            d = date(year, month, day)
            return d, f"{position.capitalize()} {p.group(2).capitalize()} {year}"
        except ValueError:
            pass
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

START_MATCHERS = [
    _match_per_direct,
    _match_specific_date,
    _match_begin_half_end,
    _match_quarter,
    _match_relative,
    _match_month_year,
]


def extract_start_date(text: str) -> tuple[Optional[date], str]:
    """
    Try to extract an assignment start date from job description text.
    Returns (date, label) or (None, "onbekend").
    """
    if not text:
        return None, "onbekend"

    for matcher in START_MATCHERS:
        result = matcher(text)
        if result:
            return result

    return None, "onbekend"


def extract_end_date(text: str) -> tuple[Optional[date], str]:
    """
    Extract assignment end date / deadline from job description text.
    Returns (date, label) or (None, "onbekend").
    """
    if not text:
        return None, "onbekend"

    # 1. "einddatum: 31-12-2025" or "eind datum 31 december 2025" or "loopt tot 15 nov 2025"
    p1 = re.search(
        r"\b(?:einddatum|eind\s+datum|loopt\s+tot|eindigt|sluitingsdatum|verlenging\s+tot)\s*:?\s*(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{4})\b",
        text, re.IGNORECASE
    )
    if p1:
        try:
            d = date(int(p1.group(3)), int(p1.group(2)), int(p1.group(1)))
            return d, f"Einddatum: {d.strftime('%d-%m-%Y')}"
        except ValueError:
            pass

    # 2. "einddatum 31 december 2025" or "tot 15 november 2025"
    p2 = re.search(
        r"\b(?:einddatum|eind\s+datum|loopt\s+tot|eindigt|sluitingsdatum|tot\s+en\s+met|tot)\s*:?\s*(\d{1,2})\s+("
        + "|".join(MONTH_MAP)
        + r")\s+(\d{4})\b",
        text, re.IGNORECASE
    )
    if p2:
        try:
            day = int(p2.group(1))
            month = MONTH_MAP[p2.group(2).lower()]
            year = int(p3 if (p3 := p2.group(3)) else date.today().year)
            d = date(year, month, day)
            return d, f"Einddatum: {day} {p2.group(2).capitalize()} {year}"
        except ValueError:
            pass

    # 3. Explicit past year check in end date context "31-12-2024" or "31-12-2025"
    p3 = re.search(r"\b(\d{1,2})[/\-\.](\d{1,2})[/\-\.](202[0-5])\b", text)
    if p3:
        try:
            d = date(int(p3.group(3)), int(p3.group(2)), int(p3.group(1)))
            return d, f"Datum uit verleden: {d.strftime('%d-%m-%Y')}"
        except ValueError:
            pass

    return None, "onbekend"


def is_within_window(
    start_date: Optional[date],
    max_months_ahead: int,
    include_unknown: bool = True,
    include_already_started: bool = False,
    end_date: Optional[date] = None,
    published_at: Optional[date] = None,
) -> tuple[bool, str]:
    """
    Check if assignment dates fall within valid future window.
    Strictly rejects past end dates, past start dates (when include_already_started=False),
    and old publication dates.
    """
    today = date.today()

    # 1. Check publication date (if older than 90 days, reject as expired listing)
    if published_at:
        if published_at < today - timedelta(days=90):
            return False, f"Vacature is te oud (gepubliceerd {published_at.isoformat()})"

    # 2. Check end date / deadline (MUST be >= today)
    if end_date:
        if end_date < today:
            return False, f"Einddatum is al verstreken ({end_date.isoformat()})"

    # 3. Check start date
    if start_date:
        if start_date < today:
            if not include_already_started:
                return False, f"Opdracht/Startdatum is in het verleden ({start_date.isoformat()})"

        cutoff = today + timedelta(days=max_months_ahead * 30)
        if start_date > cutoff:
            return (
                False,
                f"Start te ver vooruit: {start_date.isoformat()} (max {max_months_ahead}m = {cutoff.isoformat()})"
            )
        return True, f"Valid date: {start_date.isoformat()}"

    # If start_date is None
    if include_unknown:
        return True, "Startdatum onbekend (doorgelaten)"
    return False, "Geen startdatum gevonden"
