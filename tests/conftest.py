"""
Pytest configuration and shared fixtures for WerkZoeker tests.
"""

from datetime import datetime, date
import os
import tempfile
import pytest

from scrapers.base import JobItem
from filter_engine import FilterEngine

@pytest.fixture
def sample_valid_job():
    return JobItem(
        id="job-valid-001",
        title="Werkvoorbereider Elektrotechniek / E-Engineer - Freelance",
        source="TestPortal",
        url="https://example.com/job/1",
        description=(
            "Gezocht: Werkvoorbereider elektrotechniek en E-Engineer voor "
            "BIM modelleren en EPLAN E-installaties project. "
            "Opdracht op ZZP-basis, uurtarief €85-€95."
        ),
        location="Utrecht",
        rate_or_hours="€85-€95/uur",
        published_at=datetime.utcnow(),
    )

@pytest.fixture
def sample_expired_job():
    return JobItem(
        id="job-expired-002",
        title="Werkvoorbereider Elektrotechniek (Afgelopen)",
        source="TestPortal",
        url="https://example.com/job/2",
        description=(
            "Gezocht: Werkvoorbereider elektrotechniek en E-Engineer. ZZP inhuur €90/uur. "
            "EPLAN en AutoCAD. Einddatum opdracht: 31-12-2025."
        ),
        location="Amsterdam",
        published_at=datetime(2025, 6, 1),
    )

@pytest.fixture
def sample_permanent_job():
    return JobItem(
        id="job-perm-003",
        title="Elektrotechnisch Engineer - Vast Contract",
        source="TestPortal",
        url="https://example.com/job/3",
        description=(
            "Wij bieden een vast contract voor onbepaalde tijd. "
            "In loondienst met leaseauto en pensioenregeling. Werving & selectie."
        ),
        location="Rotterdam",
        published_at=datetime.utcnow(),
    )

@pytest.fixture
def filter_engine_default():
    return FilterEngine(score_threshold=5)

@pytest.fixture
def temp_db_path():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    yield path
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass
