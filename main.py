"""
WerkZoeker — Main Entry Point

Orchestrates the full scrape → filter → deduplicate → notify pipeline.
Runs on a configurable schedule via APScheduler.

Usage:
    python main.py                  # Start the scheduler (runs forever)
    python main.py --run-once       # Run one full cycle then exit
    python main.py --test-scrapers  # Test all scrapers, print results
    python main.py --test-filter    # Test filter on sample data
    python main.py --test-notify    # Send a test Telegram message
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv
from loguru import logger

# Load .env before any other imports that read env vars
load_dotenv()

from scrapers import (
    FreelanceNLScraper,
    IndeedRSSScraper,
    JobItem,
    StriiveScraper,
    WerkzoekenScraper,
    DosignScraper,
    BlueBeaverScraper,
    TechnischeVacaturebankScraper,
    VNOMScraper,
    HoofdkraanScraper,
    FreelancenetwerkScraper,
    ContinuScraper,
    MaintecScraper,
    TechnicalValleyScraper,
    MatchdScraper,
    RandstadTechniekScraper,
    TempoTeamScraper,
    SynselScraper,
    CoveboScraper,
    HeijmansScraper,
    WtbEScraper,
)
from filter_engine import FilterEngine, show_keywords
from storage import Storage
from notifier import NotifierDispatcher, TelegramNotifier
from bot_commands import TelegramCommandHandler, apply_saved_settings


# ---------------------------------------------------------------------------
# Logging Setup
# ---------------------------------------------------------------------------

def configure_logging() -> None:
    # Apply any settings saved via Telegram bot commands
    apply_saved_settings()

    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logger.remove()  # Remove default handler
    logger.add(
        sys.stderr,
        level=log_level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{line}</cyan> — "
            "<level>{message}</level>"
        ),
        colorize=True,
    )
    logger.add(
        "werkzoeker.log",
        level="DEBUG",
        rotation="10 MB",
        retention="7 days",
        compression="gz",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Scraper Registry
# ---------------------------------------------------------------------------

def get_scrapers(max_pages: int, rate_limit: float, timeout: float) -> list:
    """Return all active scraper instances (20 sources)."""
    common = dict(max_pages=max_pages, rate_limit_delay=rate_limit, timeout=timeout)
    rss_only = dict(rate_limit_delay=rate_limit, timeout=timeout)
    return [
        # RSS feeds & HTML scrapers (20 platforms total)
        FreelanceNLScraper(**rss_only),
        IndeedRSSScraper(**rss_only),
        TechnischeVacaturebankScraper(**rss_only),
        StriiveScraper(**common),
        WerkzoekenScraper(**common),
        DosignScraper(**common),
        BlueBeaverScraper(**common),
        VNOMScraper(**common),
        HoofdkraanScraper(**common),
        FreelancenetwerkScraper(**common),
        ContinuScraper(**common),
        MaintecScraper(**common),
        TechnicalValleyScraper(**common),
        MatchdScraper(**common),
        RandstadTechniekScraper(**common),
        TempoTeamScraper(**common),
        SynselScraper(**common),
        CoveboScraper(**common),
        HeijmansScraper(**common),
        WtbEScraper(**common),
    ]


# ---------------------------------------------------------------------------
# Core Pipeline
# ---------------------------------------------------------------------------

async def run_pipeline() -> dict:
    """
    Execute one full scrape → filter → store → notify cycle.
    Returns a stats dict for logging.
    """
    max_pages   = int(os.getenv("MAX_PAGES_PER_SCRAPER", "5"))
    rate_limit  = float(os.getenv("RATE_LIMIT_DELAY", "2.0"))
    timeout     = float(os.getenv("REQUEST_TIMEOUT", "30"))

    scrapers = get_scrapers(max_pages, rate_limit, timeout)
    engine   = FilterEngine()

    stats = {
        "scraped": 0,
        "passed_filter": 0,
        "new_jobs": 0,
        "notified": 0,
        "errors": 0,
        "started_at": datetime.utcnow().isoformat(),
    }

    # 1. Scrape all sources
    all_jobs: list[JobItem] = []
    for scraper in scrapers:
        try:
            async with scraper:
                jobs = await scraper.fetch_jobs()
                all_jobs.extend(jobs)
                logger.info(f"[{scraper.SOURCE_NAME}] → {len(jobs)} jobs scraped")
        except Exception as exc:
            logger.error(f"[{scraper.SOURCE_NAME}] Scraper crashed: {exc}", exc_info=True)
            stats["errors"] += 1

    stats["scraped"] = len(all_jobs)
    logger.info(f"Total scraped: {len(all_jobs)} jobs across all sources")

    if not all_jobs:
        logger.warning("No jobs scraped — check scraper connectivity")
        return stats

    # 2. Filter
    passed: list[tuple[JobItem, int, list[str]]] = []
    for job in all_jobs:
        result = engine.evaluate(job)
        if result.passed:
            passed.append((job, result.score, result.matched_keywords))

    stats["passed_filter"] = len(passed)
    logger.info(f"Filter: {len(passed)}/{len(all_jobs)} jobs passed (threshold={engine.score_threshold})")

    if not passed:
        return stats

    # 3. Deduplicate & notify
    async with Storage() as db:
        async with NotifierDispatcher() as notifier:
            for job, score, reasons in passed:
                try:
                    if not await db.is_new(job.id):
                        logger.debug(f"Duplicate skipped: '{job.title[:50]}'")
                        continue

                    # Save first (before notifying — avoids double-sends on restart)
                    await db.save_job(job, score, reasons)
                    stats["new_jobs"] += 1

                    # Send to all configured channels
                    results = await notifier.send(job, score, reasons)
                    any_ok = any(r.success for r in results)

                    if any_ok:
                        await db.mark_notified(job.id)
                        stats["notified"] += 1
                        logger.info(
                            f"✅ Notified [Telegram]: '{job.title[:55]}' "
                            f"(score={score}, start='{job.start_date_label}')"
                        )
                    else:
                        logger.warning(
                            f"⚠ All notifications failed for '{job.title[:50]}'"
                        )

                except Exception as exc:
                    logger.error(
                        f"Error processing '{job.title[:50]}': {exc}", exc_info=True
                    )
                    stats["errors"] += 1

    # 4. Log summary
    db_stats = {}
    async with Storage() as db:
        db_stats = await db.get_stats()

    logger.info(
        f"Cycle complete — scraped={stats['scraped']} | "
        f"passed={stats['passed_filter']} | "
        f"new={stats['new_jobs']} | "
        f"notified={stats['notified']} | "
        f"errors={stats['errors']} | "
        f"db_total={db_stats.get('total', '?')}"
    )
    return stats

# ---------------------------------------------------------------------------
# CLI Modes
# ---------------------------------------------------------------------------

async def test_scrapers() -> None:
    """Test all scrapers and print results to console."""
    logger.info("=== SCRAPER TEST MODE ===")
    logger.info(f"Active scrapers: Freelance.nl, Indeed NL, TechnischeVacaturebank.nl, Striive.com, Werkzoeken.nl, Dosign.nl, BlueBeaver.nl, VNOM.nl")
    max_pages  = int(os.getenv("MAX_PAGES_PER_SCRAPER", "2"))
    rate_limit = float(os.getenv("RATE_LIMIT_DELAY", "1.0"))
    timeout    = float(os.getenv("REQUEST_TIMEOUT", "30"))

    scrapers = get_scrapers(max_pages, rate_limit, timeout)
    for scraper in scrapers:
        logger.info(f"\n--- Testing: {scraper.SOURCE_NAME} ---")
        try:
            async with scraper:
                jobs = await scraper.fetch_jobs()
            logger.info(f"  → {len(jobs)} jobs returned")
            for job in jobs[:3]:  # Show first 3
                logger.info(f"     • [{job.source}] {job.title[:70]}")
                logger.info(f"       URL: {job.url}")
                logger.info(f"       Loc: {job.location}  Rate: {job.rate_or_hours}")
        except Exception as e:
            logger.error(f"  FAILED: {e}", exc_info=True)


async def test_filter() -> None:
    """Test the filter engine against synthetic and real sample jobs."""
    logger.info("=== FILTER TEST MODE ===")
    engine = FilterEngine()

    test_cases = [
        JobItem(
            id="test1",
            title="Detail Engineer Elektrotechniek - Freelance",
            source="Test",
            url="https://example.com/1",
            description=(
                "Wij zoeken een ervaren Detail Engineer voor EPLAN Pro Panel "
                "werkzaamheden op het gebied van middenspanning. "
                "Opdracht op ZZP-basis, uurtarief €85-€95. NEN 1010 kennis vereist."
            ),
        ),
        JobItem(
            id="test2",
            title="Elektrotechnisch Medewerker - Vast Contract",
            source="Test",
            url="https://example.com/2",
            description=(
                "Wij bieden een vast contract voor onbepaalde tijd. "
                "Leaseauto en pensioenregeling inbegrepen. Werving & selectie."
            ),
        ),
        JobItem(
            id="test3",
            title="E-Engineer Hoogspanning - Interim Opdracht",
            source="Test",
            url="https://example.com/3",
            description=(
                "Gezocht: E-Engineer met kennis van hoogspanning en onderstations. "
                "Transformatorstations, verdeelinrichtingen en IEC 61850. "
                "Freelance/inhuur opdracht, AutoCAD en Revit MEP vereist."
            ),
        ),
        JobItem(
            id="test4",
            title="Software Developer Python",
            source="Test",
            url="https://example.com/4",
            description="Looking for Python developer, ZZP welcome, remote work.",
        ),
    ]

    for job in test_cases:
        result = engine.evaluate(job)
        status = "✅ PASS" if result.passed else "❌ FAIL"
        logger.info(
            f"{status} | score={result.score} | '{job.title[:55]}'\n"
            f"        reason={result.rejection_reason or 'OK'}\n"
            f"        keywords={result.matched_keywords}"
        )


async def test_notify() -> None:
    """Send a test Telegram notification."""
    logger.info("=== NOTIFY TEST MODE ===")
    sample_job = JobItem(
        id="test-notify-001",
        title="Detail Engineer Elektrotechniek — TESTBERICHT",
        source="WerkZoeker Test",
        url="https://www.freelance.nl/vacatures/detail-engineer-elektrotechniek",
        description=(
            "Dit is een testbericht van WerkZoeker. "
            "De bot is correct geconfigureerd en kan Telegram-berichten versturen. "
            "EPLAN Pro Panel, hoogspanning, middenspanning, NEN 1010."
        ),
        location="Amsterdam, Noord-Holland",
        rate_or_hours="€85-€95/uur",
    )
    async with TelegramNotifier() as notifier:
        result = await notifier.send(sample_job, score=16, reasons=["eplan", "hoogspanning", "detail engineer", "nen 1010"])
        if result.success:
            logger.info("✅ Test notification sent successfully!")
        else:
            logger.error(f"❌ Test notification failed: {result.error}")


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

async def run_scheduler() -> None:
    """Start the async APScheduler loop."""
    interval_minutes = int(os.getenv("SCRAPE_INTERVAL_MINUTES", "30"))
    run_on_startup   = os.getenv("RUN_ON_STARTUP", "true").lower() == "true"

    logger.info("=" * 60)
    logger.info("  WerkZoeker 🔍⚡ — Freelance Engineering Job Bot")
    logger.info("=" * 60)
    logger.info(f"  Interval  : every {interval_minutes} minutes")
    logger.info(f"  Threshold : score ≥ {os.getenv('SCORE_THRESHOLD', '6')}")
    logger.info(f"  Database  : {os.getenv('DB_PATH', 'jobs.db')}")
    logger.info(f"  Startup run: {run_on_startup}")
    logger.info("=" * 60)

    # Start Telegram command handler as a concurrent background task
    cmd_handler = TelegramCommandHandler(run_pipeline_fn=run_pipeline)
    handler_task = asyncio.create_task(
        cmd_handler.start(),
        name="telegram_command_handler"
    )
    logger.info("[Bot] Telegram command handler task started")

    scheduler = AsyncIOScheduler(timezone="Europe/Amsterdam")
    scheduler.add_job(
        run_pipeline,
        trigger="interval",
        minutes=interval_minutes,
        id="scrape_cycle",
        name="WerkZoeker Scrape Cycle",
        max_instances=1,  # Never run two cycles simultaneously
        coalesce=True,    # Skip missed runs (e.g., after sleep/hibernate)
    )
    scheduler.start()
    logger.info(f"Scheduler started. Next run in {interval_minutes} minutes.")

    # Send startup messages to all channels
    async with NotifierDispatcher() as notifier:
        await notifier.send_startup_message()

    # Optionally run immediately on startup
    if run_on_startup:
        logger.info("Running initial scrape cycle…")
        await run_pipeline()

    # Keep the event loop alive
    try:
        while True:
            await asyncio.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutting down WerkZoeker…")
        cmd_handler.stop()
        handler_task.cancel()
        scheduler.shutdown(wait=False)


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="WerkZoeker — Autonomous Freelance Engineering Job Bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                   Start the bot (runs forever)
  python main.py --run-once        Run one full cycle then exit
  python main.py --test-scrapers   Test all scrapers
  python main.py --test-filter     Test the filter engine
  python main.py --test-notify     Send a test Telegram message
        """,
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--run-once",       action="store_true", help="Eén scan uitvoeren en stoppen")
    group.add_argument("--listen",         action="store_true", help="Luister continu naar Telegram commando's (/help, /add, etc.)")
    group.add_argument("--test-scrapers",  action="store_true", help="Alle scrapers testen")
    group.add_argument("--test-filter",    action="store_true", help="Filter engine testen met voorbeelddata")
    group.add_argument("--test-notify",    action="store_true", help="Testbericht sturen via Telegram")
    group.add_argument("--show-keywords",  action="store_true", help="Toon alle actieve trefwoorden")
    return parser.parse_args()


def main() -> None:
    configure_logging()
    args = parse_args()

    if args.test_scrapers:
        asyncio.run(test_scrapers())
    elif args.test_filter:
        asyncio.run(test_filter())
    elif args.test_notify:
        asyncio.run(test_notify())
    elif args.show_keywords:
        show_keywords()
    elif args.listen:
        logger.info("Starting Telegram command listener mode...")
        handler = TelegramCommandHandler(run_pipeline_fn=run_pipeline)
        asyncio.run(handler.start())
    elif args.run_once:
        logger.info("Running one cycle…")
        stats = asyncio.run(run_pipeline())
        logger.info(f"Done: {stats}")
    else:
        asyncio.run(run_scheduler())


if __name__ == "__main__":
    main()
