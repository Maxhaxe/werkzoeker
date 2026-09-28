"""
Unit tests for filter_engine.py
"""

import pytest
from datetime import datetime, date
from scrapers.base import JobItem
from filter_engine import FilterEngine

def test_phase_a_exclusions(filter_engine_default, sample_permanent_job):
    result = filter_engine_default.evaluate(sample_permanent_job)
    assert not result.passed
    assert "Excluded by pattern" in result.rejection_reason

def test_phase_a_freelance_indicator_missing(monkeypatch):
    monkeypatch.setenv("REQUIRE_FREELANCE_INDICATOR", "true")
    engine = FilterEngine(score_threshold=5)
    job = JobItem(
        id="job-no-zzp",
        title="Werkvoorbereider Elektrotechniek",
        source="Enginear.nl",  # Not in dedicated freelance list
        url="https://example.com/no-zzp",
        description="Werkvoorbereider elektrotechniek EPLAN en AutoCAD projecten in Utrecht.",
        published_at=datetime.utcnow(),
    )
    result = engine.evaluate(job)
    assert not result.passed
    assert "Geen freelance/ZZP/interim indicator" in result.rejection_reason

def test_phase_a_freelance_portal_bypass(filter_engine_default):
    job = JobItem(
        id="job-freelance-portal",
        title="Werkvoorbereider Elektrotechniek",
        source="Freelance.nl",  # Dedicated freelance portal
        url="https://example.com/freelance-nl",
        description="Werkvoorbereider elektrotechniek EPLAN en AutoCAD project.",
        published_at=datetime.utcnow(),
    )
    result = filter_engine_default.evaluate(job)
    assert result.passed
    assert result.score >= filter_engine_default.score_threshold

def test_phase_b_scoring_keywords(filter_engine_default, sample_valid_job):
    result = filter_engine_default.evaluate(sample_valid_job)
    assert result.passed
    assert result.score >= 5
    assert "eplan" in result.matched_keywords or "werkvoorbereider elektrotechniek" in result.matched_keywords

def test_phase_c_reject_past_end_date(filter_engine_default, sample_expired_job):
    result = filter_engine_default.evaluate(sample_expired_job)
    assert not result.passed
    reason = result.rejection_reason.lower()
    assert any(w in reason for w in ["verstreken", "verleden", "oud"])
