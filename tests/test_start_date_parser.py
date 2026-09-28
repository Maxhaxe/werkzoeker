"""
Unit tests for start_date_parser.py
"""

from datetime import date, timedelta
import pytest

from start_date_parser import extract_start_date, extract_end_date, is_within_window

def test_extract_start_date_per_direct():
    text = "Gezocht: EPLAN Engineer. Start: per direct. ZZP basis."
    d, label = extract_start_date(text)
    assert d == date.today()
    assert label == "per direct"

def test_extract_start_date_zsm():
    text = "Detail engineer elektrotechniek gezocht, z.s.m. te starten."
    d, label = extract_start_date(text)
    assert d == date.today()
    assert label == "per direct"

def test_extract_start_date_specific_date():
    text = "Startdatum: 15-11-2026. Duur: 6 maanden."
    d, label = extract_start_date(text)
    assert d == date(2026, 11, 15)
    assert "15-11-2026" in label

def test_extract_start_date_month_year():
    text = "Vanaf november 2026 zoeken wij een hardware engineer."
    d, label = extract_start_date(text)
    assert d == date(2026, 11, 1)
    assert "November 2026" in label

def test_extract_start_date_quarter():
    text = "Start in Q4 2026 voor een duur van 1 jaar."
    d, label = extract_start_date(text)
    assert d == date(2026, 10, 1)
    assert label == "Q4 2026"

def test_extract_end_date_explicit():
    text = "Opdracht: Lead Engineer. Einddatum: 31-12-2025. Standplaats Utrecht."
    d, label = extract_end_date(text)
    assert d == date(2025, 12, 31)
    assert "31-12-2025" in label

def test_extract_end_date_loopt_tot():
    text = "Interim klus loopt tot 15 november 2025 op ZZP-basis."
    d, label = extract_end_date(text)
    assert d == date(2025, 11, 15)
    assert "15 November 2025" in label

def test_is_within_window_past_end_date():
    today = date.today()
    past_end = date(2025, 12, 31)
    passed, reason = is_within_window(
        start_date=None,
        max_months_ahead=6,
        include_unknown=True,
        include_already_started=False,
        end_date=past_end
    )
    assert not passed
    assert "verstreken" in reason.lower()

def test_is_within_window_past_start_date():
    today = date.today()
    past_start = today - timedelta(days=60)
    passed, reason = is_within_window(
        start_date=past_start,
        max_months_ahead=6,
        include_unknown=True,
        include_already_started=False
    )
    assert not passed
    assert "verleden" in reason.lower()

def test_is_within_window_future_start_valid():
    today = date.today()
    future_start = today + timedelta(days=30)
    passed, reason = is_within_window(
        start_date=future_start,
        max_months_ahead=6,
        include_unknown=True,
        include_already_started=False
    )
    assert passed

def test_is_within_window_future_start_too_far():
    today = date.today()
    too_far = today + timedelta(days=360)
    passed, reason = is_within_window(
        start_date=too_far,
        max_months_ahead=6,
        include_unknown=True,
        include_already_started=False
    )
    assert not passed
    assert "vooruit" in reason.lower()

def test_is_within_window_old_publication():
    today = date.today()
    old_pub = today - timedelta(days=120)
    passed, reason = is_within_window(
        start_date=None,
        max_months_ahead=6,
        published_at=old_pub
    )
    assert not passed
    assert "oud" in reason.lower()
