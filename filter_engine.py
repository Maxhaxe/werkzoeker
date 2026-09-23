"""
WerkZoeker — Filter Engine

Three-phase filtering and scoring for job postings:

  Phase A — Hard contract-type filter
    - Exclude jobs that clearly indicate permanent employment
    - Require at least one freelance/ZZP indicator

  Phase B — Technical keyword scoring
    - Score jobs based on relevant roles, domains, tools, and norms
    - Only jobs with score >= SCORE_THRESHOLD pass through

  Phase C — Start date window check (optional)
    - Parse start date from description
    - Reject if start is beyond MAX_START_MONTHS_AHEAD
    - Unknown dates pass through by default
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loguru import logger

from scrapers.base import JobItem
from start_date_parser import extract_start_date, is_within_window

# Default path to the keywords config file
DEFAULT_KEYWORDS_FILE = "keywords.json"

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Phase A — Exclusion patterns (case-insensitive, any match = reject)
EXCLUDE_PATTERNS: list[str] = [
    "vast contract",
    "vaste aanstelling",
    "vaste baan",
    "onbepaalde tijd",
    "arbeidsovereenkomst voor onbepaalde",
    "in loondienst",
    "loondienst",
    "leaseauto",
    "pensioenregeling",
    "werving & selectie",
    "werving en selectie",
    "w&s",
    "junior trainee",
    "traineeship",
    "graduate",
    "management traineeship",
]

# Phase A — Inclusion patterns (at least one required)
INCLUDE_PATTERNS: list[str] = [
    "zzp",
    "freelance",
    "free-lance",
    "interim",
    "opdrachtbasis",
    "op opdracht",
    "uurtarief",
    "inhuur",
    "inhuuropdracht",
    "tijdelijk",
    "aannemer",
    "detachering",
    "detacheringsbureau",
    "projectbasis",
    "projectopdracht",
    "zelfstandige",
    "zelfstandig ondernemer",
    "als ondernemer",
    "das",  # "Dienst als Zelfstandige"
]

# ---------------------------------------------------------------------------
# Keyword Loading
# ---------------------------------------------------------------------------

def load_keywords(keywords_file: str | None = None) -> dict[str, int]:
    """
    Load scoring keywords from keywords.json.

    Priority order (highest wins):
      1. EXTRA_KEYWORDS env var  (e.g. "scada:3,plc:3")
      2. keywords.json [custom]  section
      3. keywords.json [roles / domains / tools / norms] sections
      4. Disabled list (removes keywords)

    Args:
        keywords_file: Path to keywords.json. Defaults to KEYWORDS_FILE env var
                       or 'keywords.json' in the current directory.

    Returns:
        dict mapping keyword → points, ready for FilterEngine.
    """
    # Resolve file path
    path = Path(
        keywords_file
        or os.getenv("KEYWORDS_FILE", DEFAULT_KEYWORDS_FILE)
    )

    keywords: dict[str, int] = {}
    disabled: set[str] = set()

    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                data: dict[str, Any] = json.load(f)

            # Load all categories dynamically (roles, domains, tools, norms, custom, etc.)
            for category, section in data.items():
                if category.startswith("_") or category == "disabled":
                    continue
                if isinstance(section, dict):
                    for key, val in section.items():
                        if key.startswith("_"):
                            continue
                        if isinstance(val, dict):
                            # Nested sub-group
                            for kw, pts in val.items():
                                if not kw.startswith("_") and isinstance(pts, (int, float)):
                                    keywords[kw.lower().strip()] = int(pts)
                        elif isinstance(val, (int, float)):
                            keywords[key.lower().strip()] = int(val)

            # Load disabled list
            for item in data.get("disabled", []):
                if isinstance(item, str) and not item.startswith("_"):
                    disabled.add(item.lower().strip())

            logger.debug(
                f"[Keywords] Loaded {len(keywords)} keywords from '{path}' "
                f"({len(disabled)} disabled)"
            )
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"[Keywords] Failed to load '{path}': {e} — using built-in defaults")
            keywords = _builtin_keywords()
    else:
        logger.warning(
            f"[Keywords] '{path}' not found — using built-in defaults. "
            f"Run 'python main.py --show-keywords' to see active keywords."
        )
        keywords = _builtin_keywords()

    # Remove disabled keywords
    for kw in disabled:
        keywords.pop(kw, None)

    # Apply EXTRA_KEYWORDS from environment (format: "trefwoord:punten,ander:4")
    extra_raw = os.getenv("EXTRA_KEYWORDS", "").strip()
    if extra_raw:
        for part in extra_raw.split(","):
            part = part.strip()
            if ":" in part:
                kw, _, pts_str = part.rpartition(":")
                try:
                    keywords[kw.lower().strip()] = int(pts_str.strip())
                    logger.debug(f"[Keywords] Extra from env: '{kw}' = {pts_str}")
                except ValueError:
                    logger.warning(f"[Keywords] Invalid EXTRA_KEYWORDS entry: '{part}'")

    if not keywords:
        logger.warning("[Keywords] No keywords loaded! Filter will score everything 0.")

    return keywords


def _builtin_keywords() -> dict[str, int]:
    """Fallback built-in keyword table (same as the distributed keywords.json)."""
    return {
        # Roles
        "detail engineer": 3, "detail engineering": 3, "lead engineer": 3,
        "senior engineer": 3, "e-engineer": 3, "elektrotechnisch engineer": 3,
        "electrical engineer": 3, "hardware engineer": 3,
        "werkvoorbereider e": 3, "werkvoorbereider elektrotechniek": 3,
        "instrumentatie engineer": 3, "installatie engineer": 3,
        "project engineer": 2, "technisch tekenaar": 2, "tekenaar": 2,
        # Domains
        "hoogspanning": 3, "hoog spanning": 3, "middenspanning": 3,
        "midden spanning": 3, "laagspanning": 3, "laag spanning": 3,
        "onderstations": 3, "onderstation": 3, "transformatorstations": 3,
        "transformatorstation": 3, "transformatoren": 2,
        "verdeelinrichtingen": 3, "verdeelinrichting": 3,
        "schakelinstallaties": 3, "schakelinstallatie": 3,
        "utiliteit": 3, "utiliteitsbouw": 3, "netinfrastructuur": 3,
        "netwerk infrastructuur": 3, "kabelberekeningen": 3, "kabelberekening": 3,
        "kortsluitingsberekening": 3, "vermogenssystemen": 2, "energiecentrale": 2,
        "elektrotechniek": 2, "elektrotechnisch": 2,
        "installatietechniek": 2, "installatietechnisch": 2,
        # Tools
        "eplan": 4, "eplan electric p8": 4, "eplan pro panel": 4,
        "autocad": 4, "autocad electrical": 4, "revit": 4, "revit mep": 4,
        "vision": 4, "dialux": 4, "dialux evo": 4, "caneco": 4, "caneco bt": 4,
        "relux": 3, "etap": 3, "digsilent": 3, "pscad": 3,
        # Norms
        "nen 1010": 2, "nen1010": 2, "nen 3140": 2, "nen3140": 2,
        "nen 3840": 2, "nen3840": 2, "iec 61850": 2, "iec61850": 2,
        "nen 3000": 2, "nen3000": 2, "atex": 2, "ip-klasse": 1, "veiligheidsklasse": 1,
    }


def show_keywords(keywords_file: str | None = None) -> None:
    """Print all active keywords grouped by point value (for --show-keywords CLI)."""
    kw = load_keywords(keywords_file)
    path = keywords_file or os.getenv("KEYWORDS_FILE", DEFAULT_KEYWORDS_FILE)
    extra = os.getenv("EXTRA_KEYWORDS", "")

    print(f"\n{'='*60}")
    print(f"  WerkZoeker — Actieve Trefwoorden")
    print(f"  Bron: {path}")
    if extra:
        print(f"  Extra (EXTRA_KEYWORDS): {extra}")
    print(f"  Totaal: {len(kw)} trefwoorden")
    print(f"  Score drempel: {os.getenv('SCORE_THRESHOLD', '6')} punten")
    print(f"{'='*60}")

    # Group by points descending
    by_pts: dict[int, list[str]] = {}
    for word, pts in sorted(kw.items(), key=lambda x: (-x[1], x[0])):
        by_pts.setdefault(pts, []).append(word)

    for pts in sorted(by_pts, reverse=True):
        words = by_pts[pts]
        print(f"\n  +{pts} punt{'en' if pts != 1 else ''}  ({len(words)} trefwoorden):")
        for i, word in enumerate(words):
            sep = "  " if (i + 1) % 4 != 0 else "\n  "
            print(f"    • {word}", end=sep)
    print("\n")

# Default threshold (overridden by .env SCORE_THRESHOLD)
DEFAULT_SCORE_THRESHOLD = 6

# Default start-date window (months ahead)
DEFAULT_MAX_START_MONTHS = 6


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class FilterResult:
    passed: bool
    score: int
    matched_keywords: list[str]
    rejection_reason: str | None = None  # set if passed=False
    start_date_label: str | None = None  # human-readable start date found in text

    def __repr__(self) -> str:
        if self.passed:
            return f"<FilterResult PASS score={self.score} kw={self.matched_keywords}>"
        return f"<FilterResult REJECT reason='{self.rejection_reason}'>"


# ---------------------------------------------------------------------------
# Filter Engine
# ---------------------------------------------------------------------------

class FilterEngine:
    """
    Three-phase filter for job postings.

    Usage:
        engine = FilterEngine(score_threshold=6)
        result = engine.evaluate(job_item)
        if result.passed:
            ...
    """

    def __init__(self, score_threshold: int | None = None, keywords_file: str | None = None):
        threshold_env = os.getenv("SCORE_THRESHOLD")
        self.score_threshold = (
            score_threshold
            if score_threshold is not None
            else (int(threshold_env) if threshold_env else DEFAULT_SCORE_THRESHOLD)
        )
        # Start date window config
        max_months_env = os.getenv("MAX_START_MONTHS_AHEAD")
        self.max_start_months = (
            int(max_months_env) if max_months_env is not None else DEFAULT_MAX_START_MONTHS
        )
        self.include_unknown_start   = os.getenv("INCLUDE_UNKNOWN_START_DATE", "true").lower() == "true"
        self.include_already_started = os.getenv("INCLUDE_ALREADY_STARTED", "true").lower() == "true"
        self.start_date_filter_active = os.getenv("MAX_START_MONTHS_AHEAD", "") != ""

        # Load keywords from file (supports live editing between runs)
        active_keywords = load_keywords(keywords_file)
        self.keywords_count = len(active_keywords)

        # Pre-compile all patterns for performance
        self._exclude_re = [
            re.compile(r"\b" + re.escape(p) + r"\b", re.IGNORECASE)
            for p in EXCLUDE_PATTERNS
        ]
        self._include_re = [
            re.compile(r"\b" + re.escape(p) + r"\b", re.IGNORECASE)
            for p in INCLUDE_PATTERNS
        ]
        self._keyword_re: list[tuple[re.Pattern, str, int]] = [
            (re.compile(re.escape(kw), re.IGNORECASE), kw, pts)
            for kw, pts in sorted(active_keywords.items(), key=lambda x: -len(x[0]))  # longest first
        ]
        logger.debug(
            f"[FilterEngine] Loaded {self.keywords_count} keywords, "
            f"threshold={self.score_threshold}, start_filter={self.start_date_filter_active}"
        )

    def evaluate(self, job: JobItem) -> FilterResult:
        """
        Evaluate a job posting through all three filter phases.
        Returns a FilterResult with pass/fail, scoring details, and start date label.
        """
        # Combine title + description for matching (title is weighted twice)
        text = f"{job.title} {job.title} {job.description}".strip().lower()

        # ---- Phase A: Hard exclusions ----
        for pattern in self._exclude_re:
            if pattern.search(text):
                reason = f"Excluded by pattern: '{pattern.pattern}'"
                logger.debug(f"[Filter] REJECT '{job.title[:50]}' — {reason}")
                return FilterResult(passed=False, score=0, matched_keywords=[], rejection_reason=reason)

        # Dedicated freelance portals skip the mandatory keyword check (their postings are 100% freelance/ZZP)
        freelance_portals = {
            "Freelance.nl", "Striive.com", "BlueBeaver.nl", "Hoofdkraan.nl",
            "Freelancenetwerk.nl", "Matchd",
        }
        is_dedicated_freelance = job.source in freelance_portals

        # ---- Phase A: Require freelance / ZZP / interim indicator ----
        require_freelance = os.getenv("REQUIRE_FREELANCE_INDICATOR", "true").lower() in ("true", "1", "yes")
        if require_freelance and not is_dedicated_freelance:
            has_freelance_indicator = any(p.search(text) for p in self._include_re)
            if not has_freelance_indicator:
                reason = "Geen freelance/ZZP/interim indicator gevonden"
                logger.debug(f"[Filter] REJECT '{job.title[:50]}' — {reason}")
                return FilterResult(passed=False, score=0, matched_keywords=[], rejection_reason=reason)

        # ---- Phase B: Technical scoring ----
        score = 0
        matched: list[str] = []
        matched_positions: set[int] = set()  # prevent double-counting overlapping matches

        for pattern, keyword, points in self._keyword_re:
            match = pattern.search(text)
            if match:
                start = match.start()
                # Check this position hasn't already been counted by a longer match
                if start not in matched_positions:
                    score += points
                    matched.append(keyword)
                    # Mark positions covered by this match
                    matched_positions.update(range(start, match.end()))

        if score < self.score_threshold:
            reason = f"Score {score} < threshold {self.score_threshold} (matched: {matched})"
            logger.debug(f"[Filter] REJECT '{job.title[:50]}' — {reason}")
            return FilterResult(passed=False, score=score, matched_keywords=matched, rejection_reason=reason)

        # ---- Phase C: Start date window check ----
        start_date, start_label = extract_start_date(text)
        # Attach to job object for use in notification message
        job.start_date_label = start_label

        if self.start_date_filter_active:
            passes_window, window_reason = is_within_window(
                start_date,
                max_months_ahead=self.max_start_months,
                include_unknown=self.include_unknown_start,
                include_already_started=self.include_already_started,
            )
            if not passes_window:
                logger.debug(f"[Filter] REJECT '{job.title[:50]}' — {window_reason}")
                return FilterResult(
                    passed=False, score=score, matched_keywords=matched,
                    rejection_reason=window_reason, start_date_label=start_label
                )

        logger.debug(f"[Filter] PASS '{job.title[:50]}' — score={score}, kw={matched}, start='{start_label}'")
        return FilterResult(passed=True, score=score, matched_keywords=matched, start_date_label=start_label)
