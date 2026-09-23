# WerkZoeker 🔍⚡

An autonomous Python bot that periodically searches for freelance/ZZP Detail Engineering jobs (elektrotechniek, utiliteit, netinfrastructuur, hoog-/middenspanning), filters them intelligently, and sends formatted notifications to Telegram.

---

## Features

- **Multi-source scraping** — RSS feeds + HTML scrapers with pluggable architecture
- **Two-phase filtering** — Contract type check + technical keyword scoring
- **Deduplication** — SQLite database prevents repeat notifications
- **Telegram notifications** — Rich, formatted messages with score & matched keywords
- **Configurable scheduler** — Runs every N minutes (default: 30)
- **Rate-limit friendly** — Polite delays and timeouts per scraper

---

## Quick Start

### 1. Prerequisites
- Python 3.11+
- A Telegram bot token (create via [@BotFather](https://t.me/BotFather))
- Your Telegram chat ID (find via [@userinfobot](https://t.me/userinfobot))

### 2. Install
```bash
# Clone / download to D:\werkzoeker
cd D:\werkzoeker

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate      # Windows
# source .venv/bin/activate  # Linux/macOS

# Install dependencies
pip install -r requirements.txt
```

### 3. Configure
```bash
# Copy the example and edit it
copy .env.example .env
notepad .env
```

Required values in `.env`:
```ini
TELEGRAM_BOT_TOKEN=your_token_from_botfather
TELEGRAM_CHAT_ID=your_chat_id
```

### 4. Run
```bash
# Start the bot (runs continuously)
python main.py

# One-time test modes
python main.py --test-scrapers    # Test all scrapers, print results
python main.py --test-filter      # Test filter engine on sample jobs
python main.py --test-notify      # Send a test Telegram message
python main.py --run-once         # Run one full cycle then exit
```

---

## Project Structure

```
werkzoeker/
├── .env                    # Your secrets (not committed)
├── .env.example            # Template
├── requirements.txt
├── main.py                 # Entry point + scheduler
│
├── scrapers/
│   ├── base.py             # BaseScraper + JobItem dataclass
│   ├── freelancenl.py      # RSS: Freelance.nl
│   ├── striive.py          # HTML: Striive.com
│   ├── werkzoeken.py       # HTML: Werkzoeken.nl
│   └── indeed_rss.py       # RSS: Indeed NL
│
├── filter_engine.py        # Phase A (contract) + Phase B (scoring)
├── storage.py              # SQLite async storage + deduplication
├── notifier.py             # Telegram Bot API sender
└── jobs.db                 # Created at runtime
```

---

## Scraper Sources

| Module | Source | Method |
|---|---|---|
| `freelancenl.py` | [Freelance.nl](https://www.freelance.nl/vacatures) | RSS Feed |
| `striive.py` | [Striive.com](https://www.striive.com/opdrachten) | HTML Scraping |
| `werkzoeken.py` | [Werkzoeken.nl](https://www.werkzoeken.nl) | HTML Scraping |
| `indeed_rss.py` | [Indeed NL](https://nl.indeed.com) | RSS Feed |

### Adding a New Scraper

1. Create `scrapers/mynewsource.py`
2. Inherit from `BaseScraper`
3. Implement `async def fetch_jobs(self) -> list[JobItem]`
4. Register it in `main.py`

```python
from scrapers.base import BaseScraper, JobItem

class MyNewScraper(BaseScraper):
    async def fetch_jobs(self) -> list[JobItem]:
        # Your implementation here
        ...
```

---

## Filter Logic

### Phase A — Contract Type (Hard Filter)
Jobs are **excluded** if they contain: `vast contract`, `onbepaalde tijd`, `leaseauto`, `pensioenregeling`, `werving & selectie`, `junior trainee`

Jobs must **include** at least one of: `zzp`, `freelance`, `interim`, `opdrachtbasis`, `uurtarief`, `inhuur`, `tijdelijk`, `aannemer`

### Phase B — Technical Scoring (Threshold: 6 points)

| Category | Keywords | Points |
|---|---|---|
| Roles | Detail Engineer, Lead Engineer, E-Engineer, Hardware Engineer, Werkvoorbereider E | +3 each |
| Domains | Hoogspanning, middenspanning, laagspanning, onderstations, transformatorstations, verdeelinrichtingen, utiliteit, netinfrastructuur, kabelberekeningen | +3 each |
| Software | EPLAN, AutoCAD, Revit, Dialux, Caneco, Vision | +4 each |
| Norms | NEN 1010, NEN 3140, NEN 3840, IEC 61850 | +2 each |

---

## Telegram Message Format

```
⚡ Nieuwe Opdracht: Detail Engineer Hoogspanning

Bron: Striive.com | Locatie: Amsterdam
Match Score: 13 (eplan, hoogspanning, detail engineer)
Indicatie: €85-€95/uur

"Wij zoeken een ervaren Detail Engineer voor een project bij een groot..."

🔗 Bekijk Opdracht
```

---

## Configuration Reference

| Variable | Default | Description |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | — | **Required.** Bot token from BotFather |
| `TELEGRAM_CHAT_ID` | — | **Required.** Target chat/group ID |
| `SCRAPE_INTERVAL_MINUTES` | `30` | How often to run (minutes) |
| `RUN_ON_STARTUP` | `true` | Run immediately when bot starts |
| `DB_PATH` | `jobs.db` | Path to SQLite database |
| `LOG_LEVEL` | `INFO` | Logging verbosity |
| `MAX_PAGES_PER_SCRAPER` | `5` | Max pages to paginate |
| `RATE_LIMIT_DELAY` | `2.0` | Seconds between paginated requests |
| `REQUEST_TIMEOUT` | `30` | HTTP request timeout |
| `SCORE_THRESHOLD` | `6` | Minimum score for notification |

---

## Troubleshooting

**Bot doesn't send messages:**
- Check `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env`
- Make sure you've started a conversation with the bot first (send `/start`)
- For groups/channels, the bot must be an admin

**Scraper returns no results:**
- Run `python main.py --test-scrapers` to see per-scraper output
- Some sites may block requests; check `LOG_LEVEL=DEBUG` for details

**All jobs filtered out:**
- Lower `SCORE_THRESHOLD` temporarily and check the logs
- Run `python main.py --test-filter` to see scoring details
