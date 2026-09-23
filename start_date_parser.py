"""
WerkZoeker — Start Date Parser

Extracts assignment start date information from Dutch (and English) job
description text. Returns a parsed date (or None) and a human-readable label.

Recognised patterns:
  - "per direct" / "z.s.m." / "zo snel mogelijk" → today
  - "per 1 oktober 2026" / "vanaf oktober" → specific month
  - "Q1 2027" / "4e kwartaal 2026" → estimated quarter start
  - "over 3 maanden" → relative date
  - "begin/half/eind [month]" → approximate month position
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

def _current_year() -> int:
    return date.today().year


def _resolve_year(raw_year: str | None) -> int:
    """Return a plausible year: prefer explicit, otherwise current or next."""
    today = date.today()
    if raw_year:
        y = int(raw_year)
        # Accept years 2020–2035
        if 2020 <= y <= 2035:
            return y
    # Default: if we're in Nov/Dec suggest next year, else current
    return today.year if today.month <= 10 else today.year + 1


# ---------------------------------------------------------------------------
# Pattern matchers (ordered by specificity, most specific first)
# ---------------------------------------------------------------------------

def _match_per_direct(text: str) -> Optional[tuple[date, str]]:
    patterns = [
        r"\bper\s+direct\b",
        r"\bz\.?\s*s\.?\s*m\.?\b",         # z.s.m. / zsm
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
    """Match patterns like 'per 1 oktober 2026', 'vanaf 15 nov', '01-10-2026'."""
    # Pattern: day month year
    p1 = re.search(
        r"\b(\d{1,2})\s+(" + "|".join(MONTH_MAP) + r")\s*(\d{4})?\b",
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

    # Pattern: DD-MM-YYYY or DD/MM/YYYY
    p2 = re.search(r"\b(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{4})\b", text)
    if p2:
        try:
            d = date(int(p2.group(3)), int(p2.group(2)), int(p2.group(1)))
            return d, d.strftime("%d-%m-%Y")
        except ValueError:
            pass

    return None


def _match_month_year(text: str) -> Optional[tuple[date, str]]:
    """Match 'oktober 2026', 'start in november', 'vanaf maart'."""
    p = re.search(
        r"\b(?:per|vanaf|start(?:datum)?|begin|in)?\s*("
        + "|".join(MONTH_MAP)
        + r")\s*(\d{4})?\b",
        text, re.IGNORECASE
    )
    if p:
        month = MONTH_MAP[p.group(1).lower()]
        year = _resolve_year(p.group(2))
        try:
            d = date(year, month, 1)
            label = f"~{p.group(1).capitalize()} {year}"
            return d, label
        except ValueError:
            pass
    return None


def _match_quarter(text: str) -> Optional[tuple[date, str]]:
    """Match 'Q3 2026', '3e kwartaal 2026', 'vierde kwartaal'."""
    word_to_q = {
        "eerste": 1, "1e": 1, "eerste kwartaal": 1,
        "tweede": 2, "2e": 2, "tweede kwartaal": 2,
        "derde": 3, "3e": 3, "derde kwartaal": 3,
        "vierde": 4, "4e": 4, "vierde kwartaal": 4,
    }
    # Q1/Q2/Q3/Q4
    p1 = re.search(r"\bQ([1-4])\s*(\d{4})?\b", text, re.IGNORECASE)
    if p1:
        q = int(p1.group(1))
        year = _resolve_year(p1.group(2))
        month = QUARTER_TO_MONTH[q]
        d = date(year, month, 1)
        return d, f"Q{q} {year}"

    # "3e kwartaal 2026"
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
    """Match 'over 3 maanden', 'binnen 6 weken', 'in 2 maanden'."""
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
            # Approximate: n months = n * 30 days
            d = today + timedelta(days=n * 30)
            label = f"over ~{n} maanden"
        return d, label
    return None


def _match_begin_half_end(text: str) -> Optional[tuple[date, str]]:
    """Match 'begin oktober', 'half november 2026', 'eind Q3'."""
    p = re.search(
        r"\b(begin|half|midden|eind(?:e)?)\s+(" + "|".join(MONTH_MAP) + r")\s*(\d{4})?\b",
        text, re.IGNORECASE
    )
    if p:
        position = p.group(1).lower()
        month = MONTH_MAP[p.group(2).lower()]
        year = _resolve_year(p.group(3))
        if "begin" in position:
            day = 1
        elif "half" in position or "midden" in position:
            day = 15
        else:  # eind
            day = 25
        try:
            d = date(year, month, day)
            return d, f"{position.capitalize()} {p.group(2).capitalize()} {year}"
        except ValueError:
            pass
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

MATCHERS = [
    _match_per_direct,
    _match_specific_date,
    _match_begin_half_end,
    _match_quarter,
    _match_relative,
    _match_month_year,   # most general — run last
]


def extract_start_date(text: str) -> tuple[Optional[date], str]:
    """
    Try to extract an assignment start date from job description text.

    Returns:
        (date, label)  — date is the estimated start, label is human-readable
        (None, "onbekend")  — if no date found
    """
    if not text:
        return None, "onbekend"

    # Run matchers in order of specificity
    for matcher in MATCHERS:
        result = matcher(text)
        if result:
            parsed_date, label = result
            return parsed_date, label

    return None, "onbekend"


def is_within_window(
    start_date: Optional[date],
    max_months_ahead: int,
    include_unknown: bool = True,
    include_already_started: bool = True,
) -> tuple[bool, str]:
    """
    Check if a start date falls within the acceptable window.

    Args:
        start_date: Parsed start date (or None if unknown)
        max_months_ahead: Maximum months in the future to accept (0 = per direct only)
        include_unknown: If True, pass jobs with no detected start date
        include_already_started: If True, pass jobs that have already started

    Returns:
        (passes: bool, reason: str)
    """
    if start_date is None:
        if include_unknown:
            return True, "Startdatum onbekend (doorgelaten)"
        return False, "Geen startdatum gevonden"

    today = date.today()

    if start_date < today:
        if include_already_started:
            return True, f"Al gestart ({start_date.isoformat()})"
        return False, f"Opdracht al begonnen ({start_date.isoformat()})"

    cutoff = today + timedelta(days=max_months_ahead * 30)
    if start_date <= cutoff:
        return True, f"Start binnen {max_months_ahead} maanden"

    return (
        False,
        f"Start te ver vooruit: {start_date.isoformat()} "
        f"(max {max_months_ahead} maanden = {cutoff.isoformat()})"
    )
