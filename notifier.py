"""
WerkZoeker — Telegram Notifier (Telegram Only)

Sends formatted job match notifications to a Telegram chat
using the Bot API's sendMessage endpoint via direct HTTP requests.

Features:
  - MarkdownV2 formatted messages with all job details
  - Start date label in notification
  - Automatic rate limiting (Telegram: 30 messages/second per bot)
  - Retry logic with exponential backoff
  - Startup and summary messages
"""

from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass

import httpx
from loguru import logger

from scrapers.base import JobItem

# Telegram Bot API base URL
TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}/sendMessage"

# Rate limit: 50ms between messages → ~20 msgs/sec (limit is 30/sec)
MESSAGE_DELAY_SECONDS = 0.05

# Retry settings
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2.0


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class NotifyResult:
    success: bool
    job_id: str
    error: str | None = None


# ---------------------------------------------------------------------------
# Telegram Notifier
# ---------------------------------------------------------------------------

class TelegramNotifier:
    """
    Sends Telegram notifications for matched job postings.

    Usage:
        async with TelegramNotifier() as notifier:
            result = await notifier.send(job, score=10, reasons=["eplan"])
    """

    def __init__(
        self,
        bot_token: str | None = None,
        chat_id: str | None = None,
    ):
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id   = chat_id   or os.getenv("TELEGRAM_CHAT_ID", "")
        self._api_url  = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        self._client: httpx.AsyncClient | None = None

        if not self.bot_token or self.bot_token == "123456789:ABCdefGHIjklMNOpqrSTUvwxYZ":
            logger.warning("[Notifier] TELEGRAM_BOT_TOKEN not configured!")
        if not self.chat_id:
            logger.warning("[Notifier] TELEGRAM_CHAT_ID not configured!")

    @property
    def is_configured(self) -> bool:
        placeholder = "123456789:ABCdefGHIjklMNOpqrSTUvwxYZ"
        return bool(self.bot_token and self.bot_token != placeholder and self.chat_id)

    async def __aenter__(self) -> "TelegramNotifier":
        self._client = httpx.AsyncClient(timeout=15.0)
        return self

    async def __aexit__(self, *args) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    async def send(self, job: JobItem, score: int, reasons: list[str]) -> NotifyResult:
        """Send a notification for a single matched job."""
        if not self.is_configured:
            logger.error("[Notifier] Missing bot token or chat ID — cannot send notification")
            return NotifyResult(success=False, job_id=job.id, error="Missing credentials")

        message = self._format_message(job, score, reasons)
        result = await self._send_with_retry(job.id, message)
        return result

    async def send_startup_message(self) -> None:
        """Send a startup notification to confirm the bot is running."""
        text = (
            "🤖 *WerkZoeker gestart\\!*\n"
            "De bot is actief en zoekt naar freelance opdrachten\\.\n"
            "Ik stuur je een bericht zodra er relevante matches zijn\\."
        )
        await self._send_raw(text)

    async def send_summary(self, found: int, total_scraped: int) -> None:
        """Send a brief scan summary."""
        text = (
            f"📊 *Scan voltooid*\n"
            f"Gescand: {self._esc(str(total_scraped))} \\| "
            f"Nieuwe matches: {self._esc(str(found))}"
        )
        await self._send_raw(text)

    async def send_raw(self, text: str, job_id: str = "system") -> NotifyResult:
        """Send arbitrary pre-formatted text."""
        return await self._send_with_retry(job_id, text)

    # -----------------------------------------------------------------------
    # Message Formatting
    # -----------------------------------------------------------------------

    def _format_message(self, job: JobItem, score: int, reasons: list[str]) -> str:
        """
        Format a job match as a Telegram MarkdownV2 message.

        ⚡ *Nieuwe Opdracht: Detail Engineer Hoogspanning*
        *Bron:* Striive.com | *Locatie:* Amsterdam
        *Score:* 13 (eplan, hoogspanning, detail engineer)
        *Startdatum:* ~Oktober 2026
        *Indicatie:* €85-€95/uur

        _"Wij zoeken een ervaren Detail Engineer..."_

        🔗 [Bekijk Opdracht](url)
        """
        title     = self._esc(job.title)
        source    = self._esc(job.source)
        location  = self._esc(job.location or "Onbekend")
        score_s   = self._esc(str(score))
        reasons_s = self._esc(", ".join(reasons[:6]))

        lines = [
            f"⚡ *Nieuwe Opdracht: {title}*",
            f"*Bron:* {source} \\| *Locatie:* {location}",
            f"*Score:* {score_s} \\({reasons_s}\\)",
        ]

        if job.start_date_label and job.start_date_label != "onbekend":
            lines.append(f"*Startdatum:* {self._esc(job.start_date_label)}")

        if job.rate_or_hours:
            lines.append(f"*Indicatie:* {self._esc(job.rate_or_hours)}")

        snippet = self._get_snippet(job.description)
        if snippet:
            lines.append(f"\n_{self._esc(snippet)}_")

        lines.append(f"\n🔗 [Bekijk Opdracht]({job.url})")
        return "\n".join(lines)

    @staticmethod
    def _esc(text: str) -> str:
        """Escape special characters for Telegram MarkdownV2."""
        special = r"\_*[]()~`>#+-=|{}.!"
        return re.sub(r"([" + re.escape(special) + r"])", r"\\\1", text)

    @staticmethod
    def _get_snippet(description: str, max_chars: int = 300) -> str:
        """Extract a clean 2-sentence snippet from the description."""
        if not description:
            return ""
        sentences = re.split(r"(?<=[.!?])\s+", description.strip())
        snippet = ""
        for sentence in sentences:
            if len(snippet) + len(sentence) + 1 <= max_chars:
                snippet += (" " if snippet else "") + sentence
            else:
                break
        if not snippet and description:
            snippet = description[:max_chars].rstrip() + "…"
        return snippet.strip()

    # -----------------------------------------------------------------------
    # HTTP / Retry Logic
    # -----------------------------------------------------------------------

    async def _send_raw(self, text: str) -> None:
        """Send raw text without tracking job_id."""
        if not self.is_configured:
            return
        async with httpx.AsyncClient(timeout=15.0) as client:
            self._client = client
            await self._send_with_retry("system", text)
            self._client = None

    async def _send_with_retry(self, job_id: str, text: str) -> NotifyResult:
        """Send a message with exponential backoff on failure, supporting multiple chat IDs."""
        client = self._client
        own_client = False
        if client is None:
            client = httpx.AsyncClient(timeout=15.0)
            own_client = True

        chat_ids = [c.strip() for c in self.chat_id.split(",") if c.strip()]
        any_success = False
        last_error = None

        try:
            for target_chat in chat_ids:
                for attempt in range(1, MAX_RETRIES + 1):
                    try:
                        response = await client.post(
                            self._api_url,
                            json={
                                "chat_id": target_chat,
                                "text": text,
                                "parse_mode": "MarkdownV2",
                                "disable_web_page_preview": False,
                            },
                        )
                        data = response.json()

                        if response.status_code == 200 and data.get("ok"):
                            await asyncio.sleep(MESSAGE_DELAY_SECONDS)
                            any_success = True
                            break

                        if response.status_code == 429:
                            retry_after = data.get("parameters", {}).get("retry_after", 5)
                            logger.warning(f"[Notifier] Rate limited — waiting {retry_after}s")
                            await asyncio.sleep(retry_after)
                            continue

                        error_desc = data.get("description", str(data))
                        last_error = f"{response.status_code} — {error_desc}"
                        logger.warning(
                            f"[Notifier] API error for {target_chat} (attempt {attempt}/{MAX_RETRIES}): {last_error}"
                        )

                    except httpx.RequestError as e:
                        last_error = str(e)
                        logger.warning(f"[Notifier] Request error for {target_chat} (attempt {attempt}/{MAX_RETRIES}): {e}")

                    if attempt < MAX_RETRIES:
                        await asyncio.sleep(RETRY_BACKOFF_BASE ** attempt)

            if any_success:
                return NotifyResult(success=True, job_id=job_id)
            else:
                return NotifyResult(success=False, job_id=job_id, error=last_error or f"Failed after {MAX_RETRIES} attempts")
        finally:
            if own_client:
                await client.aclose()


# ---------------------------------------------------------------------------
# NotifierDispatcher — kept for API compatibility, Telegram-only
# ---------------------------------------------------------------------------

class NotifierDispatcher:
    """
    Thin wrapper around TelegramNotifier.
    Kept for API compatibility with main.py.
    """

    def __init__(self):
        self._notifier = TelegramNotifier()
        self._open = False

    async def __aenter__(self) -> "NotifierDispatcher":
        await self._notifier.__aenter__()
        self._open = True
        if self._notifier.is_configured:
            logger.info("[Notifier] Telegram channel active ✅")
        else:
            logger.error("[Notifier] Telegram not configured! Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID.")
        return self

    async def __aexit__(self, *args) -> None:
        await self._notifier.__aexit__(*args)
        self._open = False

    async def send(self, job: JobItem, score: int, reasons: list[str]) -> list[NotifyResult]:
        result = await self._notifier.send(job, score, reasons)
        return [result]

    async def send_startup_message(self) -> None:
        await self._notifier.send_startup_message()

    async def send_summary(self, found: int, total_scraped: int) -> None:
        await self._notifier.send_summary(found, total_scraped)

    @property
    def any_success(self) -> bool:
        return self._notifier.is_configured
