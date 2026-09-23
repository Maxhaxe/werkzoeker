"""
WerkZoeker — Scrapers Package
"""

from .base import BaseScraper, JobItem
from .freelancenl import FreelanceNLScraper
from .striive import StriiveScraper
from .werkzoeken import WerkzoekenScraper
from .indeed_rss import IndeedRSSScraper
from .dosign import DosignScraper
from .bluebeaver import BlueBeaverScraper
from .technischevacaturebank import TechnischeVacaturebankScraper
from .vnom import VNOMScraper
from .hoofdkraan import HoofdkraanScraper
from .freelancenetwerk import FreelancenetwerkScraper

from .continu import ContinuScraper
from .maintec import MaintecScraper
from .technicalvalley import TechnicalValleyScraper
from .matchd import MatchdScraper
from .randstadtechniek import RandstadTechniekScraper
from .tempoteam import TempoTeamScraper
from .synsel import SynselScraper
from .covebo import CoveboScraper
from .heijmans import HeijmansScraper
from .wtbe import WtbEScraper

__all__ = [
    "BaseScraper",
    "JobItem",
    "FreelanceNLScraper",
    "StriiveScraper",
    "WerkzoekenScraper",
    "IndeedRSSScraper",
    "DosignScraper",
    "BlueBeaverScraper",
    "TechnischeVacaturebankScraper",
    "VNOMScraper",
    "HoofdkraanScraper",
    "FreelancenetwerkScraper",
    "ContinuScraper",
    "MaintecScraper",
    "TechnicalValleyScraper",
    "MatchdScraper",
    "RandstadTechniekScraper",
    "TempoTeamScraper",
    "SynselScraper",
    "CoveboScraper",
    "HeijmansScraper",
    "WtbEScraper",
]
