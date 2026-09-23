"""
WerkZoeker — Telegram Command Handler (Long Polling)

Listens for incoming Telegram messages and handles bot commands.
Runs concurrently with the scheduler in the same asyncio event loop.

Security: Only accepts commands from the configured TELEGRAM_CHAT_ID.
All other senders receive no response (silent drop).

Supported commands:
    /help               — show all available commands
    /status             — bot status + database statistics
    /keywords           — show all active scoring keywords
    /add woord:punten   — add or update a keyword
    /remove woord       — delete a keyword from keywords.json
    /disable woord      — add keyword to the disabled list
    /threshold <n>      — change the score threshold
    /start <n>          — set start-date window in months (0 = disable)
    /run                — trigger an immediate scrape cycle
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Callable, Awaitable

import httpx
from loguru import logger

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

POLL_INTERVAL    = 2.0    # seconds between getUpdates calls
POLL_TIMEOUT     = 30     # long-poll timeout (server holds connection)
MAX_POLL_ERRORS  = 5      # consecutive errors before backing off


# ---------------------------------------------------------------------------
# Command Handler
# ---------------------------------------------------------------------------

class TelegramCommandHandler:
    """
    Polls Telegram for new messages and dispatches bot commands.

    Usage:
        handler = TelegramCommandHandler(run_pipeline_fn=run_pipeline)
        await handler.start()          # runs forever (call from asyncio task)
    """

    def __init__(self, run_pipeline_fn: Callable[[], Awaitable[dict]] | None = None):
        self._bot_token  = None
        self._chat_id    = None
        self.keywords_file = Path(os.getenv("KEYWORDS_FILE", "keywords.json"))
        self._run_pipeline = run_pipeline_fn
        self._offset     = 0   # Telegram update_id offset for getUpdates
        self._client: httpx.AsyncClient | None = None
        self._running    = False

    @property
    def bot_token(self) -> str:
        return self._bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")

    @property
    def chat_id(self) -> str:
        return self._chat_id or os.getenv("TELEGRAM_CHAT_ID", "")

    @property
    def _api(self) -> str:
        return f"https://api.telegram.org/bot{self.bot_token}"

    # -----------------------------------------------------------------------
    # Lifecycle
    # -----------------------------------------------------------------------

    async def start(self) -> None:
        """Start the long-poll loop. Runs until cancelled."""
        if not self.bot_token or not self.chat_id:
            logger.warning("[Bot] Telegram not configured — command handler disabled")
            return

        logger.info("[Bot] Command handler started. Listening for Telegram commands…")
        self._running = True
        error_count = 0

        async with httpx.AsyncClient(timeout=POLL_TIMEOUT + 5) as client:
            self._client = client
            while self._running:
                try:
                    updates = await self._get_updates()
                    error_count = 0
                    for update in updates:
                        await self._handle_update(update)
                except asyncio.CancelledError:
                    logger.info("[Bot] Command handler cancelled")
                    break
                except Exception as e:
                    error_count += 1
                    backoff = min(2 ** error_count, 60)
                    logger.warning(
                        f"[Bot] Poll error #{error_count}: {e}. "
                        f"Backing off {backoff}s…"
                    )
                    await asyncio.sleep(backoff)

        self._running = False
        self._client = None

    def stop(self) -> None:
        self._running = False

    async def process_pending_updates(self) -> int:
        """
        Fetch and process any unhandled pending updates non-blockingly.
        Returns the number of processed updates.
        """
        if not self.bot_token or not self.chat_id:
            return 0

        processed = 0
        async with httpx.AsyncClient(timeout=10.0) as client:
            self._client = client
            try:
                resp = await client.get(
                    f"{self._api}/getUpdates",
                    params={"offset": self._offset, "timeout": 0, "allowed_updates": ["message"]},
                )
                data = resp.json()
                if data.get("ok"):
                    updates = data.get("result", [])
                    for update in updates:
                        self._offset = update["update_id"] + 1
                        await self._handle_update(update)
                        processed += 1
            except Exception as e:
                logger.warning(f"[Bot] Pending updates check failed: {e}")
            finally:
                self._client = None
        return processed

    # -----------------------------------------------------------------------
    # Telegram API
    # -----------------------------------------------------------------------

    async def _get_updates(self) -> list[dict]:
        """Long-poll Telegram for new updates."""
        resp = await self._client.get(
            f"{self._api}/getUpdates",
            params={
                "offset": self._offset,
                "timeout": POLL_TIMEOUT,
                "allowed_updates": ["message"],
            },
        )
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"getUpdates error: {data.get('description')}")

        updates = data.get("result", [])
        if updates:
            self._offset = updates[-1]["update_id"] + 1
        return updates

    async def _send(self, text: str, parse_mode: str = "HTML") -> None:
        """Send a reply to the configured chat."""
        try:
            await self._client.post(
                f"{self._api}/sendMessage",
                json={
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": parse_mode,
                    "disable_web_page_preview": True,
                },
                timeout=10,
            )
        except Exception as e:
            logger.warning(f"[Bot] Failed to send reply: {e}")

    # -----------------------------------------------------------------------
    # Update Dispatcher
    # -----------------------------------------------------------------------

    async def _handle_update(self, update: dict) -> None:
        msg = update.get("message", {})
        text = (msg.get("text") or "").strip()
        chat_id = str(msg.get("chat", {}).get("id", ""))

        if not text or not chat_id:
            return

        # Security: only respond to the configured chat
        if chat_id != str(self.chat_id):
            logger.debug(f"[Bot] Ignored message from unauthorized chat {chat_id}")
            return

        logger.info(f"[Bot] Command received: '{text}'")

        # Parse command
        parts  = text.split(None, 1)
        cmd    = parts[0].lower().lstrip("/").split("@")[0]  # strip @botname suffix
        args   = parts[1].strip() if len(parts) > 1 else ""

        handlers = {
            "help":        self._cmd_help,
            "start":       self._cmd_start,   # /start is also Telegram's default
            "status":      self._cmd_status,
            "platformen":  self._cmd_platformen,
            "bronnen":     self._cmd_platformen,
            "keywords":    self._cmd_keywords,
            "add":         self._cmd_add,
            "remove":      self._cmd_remove,
            "disable":     self._cmd_disable,
            "threshold":   self._cmd_threshold,
            "startdatum":  self._cmd_startfilter,
            "startfilter": self._cmd_startfilter,
            "run":         self._cmd_run,
        }

        handler = handlers.get(cmd)
        if handler:
            await handler(args)
        else:
            await self._send(
                f"❓ Onbekend commando: <code>/{cmd}</code>\n"
                f"Typ <b>/help</b> voor een overzicht."
            )

    # -----------------------------------------------------------------------
    # Command Implementations
    # -----------------------------------------------------------------------

    async def _cmd_help(self, _args: str) -> None:
        await self._send(
            "⚡ <b>WerkZoeker — Commando's</b>\n\n"
            "<b>Informatie & Bronnen</b>\n"
            "/status — Bot status &amp; statistieken\n"
            "/platformen — Overzicht van alle 8 databronnen\n"
            "/keywords — Toon alle actieve trefwoorden\n\n"
            "<b>Trefwoorden beheren</b>\n"
            "/add <i>woord:punten</i> — Voeg trefwoord toe\n"
            "  <i>Voorbeeld: /add scada:3</i>\n"
            "/remove <i>woord</i> — Verwijder trefwoord\n"
            "/disable <i>woord</i> — Zet trefwoord uit\n\n"
            "<b>Filter instellingen</b>\n"
            "/threshold <i>getal</i> — Verander score drempel\n"
            "  <i>Voorbeeld: /threshold 8</i>\n"
            "/startfilter <i>maanden</i> — Startdatum filter\n"
            "  <i>/startfilter 3 = max 3 maanden vooruit</i>\n"
            "  <i>/startfilter 0 = filter uitschakelen</i>\n\n"
            "<b>Acties</b>\n"
            "/run — Voer direct een scan uit\n\n"
            f"📂 Trefwoorden bestand: <code>keywords.json</code>"
        )

    async def _cmd_platformen(self, _args: str) -> None:
        """Show all 8 supported job platforms."""
        await self._send(
            "🌐 <b>Ondersteunde Databronnen &amp; Platformen</b> (8 totaal)\n\n"
            "1️⃣ <b>Freelance.nl</b> — Freelance opdrachten &amp; projecten\n"
            "2️⃣ <b>Striive.com</b> — Interim &amp; freelance marktplaats\n"
            "3️⃣ <b>Werkzoeken.nl</b> — Vacatures &amp; ZZP opdrachten\n"
            "4️⃣ <b>Dosign.nl</b> — Engineering &amp; techniek opdrachten\n"
            "5️⃣ <b>BlueBeaver.nl</b> — Freelance engineering projecten\n"
            "6️⃣ <b>TechnischeVacaturebank.nl</b> — Technische vacatures\n"
            "7️⃣ <b>VNOM.nl</b> — Bemiddeling in techniek &amp; ZZP\n"
            "8️⃣ <b>Indeed NL</b> — Aggregator vacatures\n\n"
            "<i>De bot scant alle bronnen periodiek en filtert automatisch op contractvorm (ZZP/freelance) en technische trefwoorden.</i>"
        )

    async def _cmd_start(self, args: str) -> None:
        """Handle /start (Telegram default) — show welcome + help."""
        if args:
            # If called as /start with args it might be from startfilter alias
            await self._cmd_startfilter(args)
        else:
            await self._send(
                "👋 <b>WerkZoeker actief!</b>\n"
                "Typ /help voor een overzicht van alle commando's."
            )

    async def _cmd_status(self, _args: str) -> None:
        """Show bot status and database statistics."""
        from storage import Storage
        from filter_engine import load_keywords

        keywords = load_keywords(str(self.keywords_file))
        threshold = os.getenv("SCORE_THRESHOLD", "6")
        start_filter = os.getenv("MAX_START_MONTHS_AHEAD", "uitgeschakeld")
        interval = os.getenv("SCRAPE_INTERVAL_MINUTES", "30")
        channels = os.getenv("NOTIFY_CHANNELS", "telegram,whatsapp")

        try:
            async with Storage() as db:
                stats = await db.get_stats()
            db_text = (
                f"📊 <b>Database:</b>\n"
                f"  Totaal gevonden: {stats['total']}\n"
                f"  Verstuurd: {stats['notified']}\n"
                f"  In wachtrij: {stats['pending']}"
            )
        except Exception:
            db_text = "📊 <b>Database:</b> Niet beschikbaar"

        await self._send(
            "🤖 <b>WerkZoeker Status</b>\n\n"
            f"⏱ Interval: elke {interval} minuten\n"
            f"🎯 Score drempel: {threshold} punten\n"
            f"📅 Startdatum filter: {start_filter} maanden\n"
            f"📡 Kanalen: {channels}\n"
            f"🔤 Trefwoorden: {len(keywords)} actief\n\n"
            f"{db_text}"
        )

    async def _cmd_keywords(self, _args: str) -> None:
        """Show all active keywords grouped by score."""
        from filter_engine import load_keywords

        kw = load_keywords(str(self.keywords_file))

        # Group by points
        by_pts: dict[int, list[str]] = {}
        for word, pts in sorted(kw.items(), key=lambda x: (-x[1], x[0])):
            by_pts.setdefault(pts, []).append(word)

        lines = [f"🔤 <b>Actieve trefwoorden</b> ({len(kw)} totaal)\n"]
        for pts in sorted(by_pts, reverse=True):
            words = by_pts[pts]
            label = f"  <b>+{pts} {'punt' if pts == 1 else 'punten'}</b> ({len(words)}):"
            wordlist = ", ".join(f"<code>{w}</code>" for w in words)
            lines.append(f"{label}\n  {wordlist}\n")

        # Telegram message limit ~4096 chars — split if needed
        full_text = "\n".join(lines)
        if len(full_text) > 3900:
            full_text = full_text[:3900] + "\n\n<i>… (te lang, zie keywords.json voor volledig overzicht)</i>"

        await self._send(full_text)

    async def _cmd_add(self, args: str) -> None:
        """
        /add woord:punten  — Add or update a keyword.
        Examples:
            /add scada:3
            /add substation automation:4
        """
        if ":" not in args:
            await self._send(
                "❌ Gebruik: <code>/add trefwoord:punten</code>\n"
                "Voorbeeld: <code>/add scada:3</code>"
            )
            return

        word, _, pts_str = args.strip().rpartition(":")
        word = word.strip().lower()
        pts_str = pts_str.strip()

        if not word:
            await self._send("❌ Trefwoord mag niet leeg zijn.")
            return

        try:
            pts = int(pts_str)
            if pts < 1 or pts > 10:
                raise ValueError("out of range")
        except ValueError:
            await self._send(
                f"❌ Ongeldige puntenwaarde: <code>{pts_str}</code>\n"
                "Gebruik een getal tussen 1 en 10."
            )
            return

        # Update keywords.json
        data = self._load_json()
        custom = data.setdefault("custom", {})

        # Remove from disabled list if it was there
        disabled = data.get("disabled", [])
        data["disabled"] = [d for d in disabled if d != word]

        custom[word] = pts
        self._save_json(data)

        logger.info(f"[Bot] Added keyword: '{word}' = {pts}")
        await self._send(
            f"✅ Trefwoord toegevoegd:\n"
            f"  <code>{word}</code> → <b>+{pts} punten</b>\n\n"
            f"Actief vanaf de volgende scan."
        )

    async def _cmd_remove(self, args: str) -> None:
        """
        /remove woord  — Permanently delete a keyword from keywords.json.
        """
        word = args.strip().lower()
        if not word:
            await self._send("❌ Gebruik: <code>/remove trefwoord</code>")
            return

        data   = self._load_json()
        found  = False

        # Remove from all categories
        for category in ("roles", "domains", "tools", "norms"):
            if word in data.get(category, {}):
                del data[category][word]
                found = True

        # Remove from custom
        custom = data.get("custom", {})
        if word in custom:
            del custom[word]
            found = True
        # Also check nested custom groups
        for key, val in list(custom.items()):
            if isinstance(val, dict) and word in val:
                del val[word]
                found = True

        if found:
            self._save_json(data)
            logger.info(f"[Bot] Removed keyword: '{word}'")
            await self._send(
                f"🗑 Trefwoord verwijderd: <code>{word}</code>\n"
                f"Actief vanaf de volgende scan."
            )
        else:
            await self._send(
                f"⚠️ Trefwoord <code>{word}</code> niet gevonden in keywords.json.\n"
                f"Gebruik /keywords om de lijst te bekijken."
            )

    async def _cmd_disable(self, args: str) -> None:
        """
        /disable woord  — Add keyword to the disabled list (keeps it in file but ignores it).
        """
        word = args.strip().lower()
        if not word:
            await self._send("❌ Gebruik: <code>/disable trefwoord</code>")
            return

        data     = self._load_json()
        disabled = [d for d in data.get("disabled", []) if not d.startswith("_")]
        if word not in disabled:
            disabled.append(word)
            data["disabled"] = disabled
            self._save_json(data)
            logger.info(f"[Bot] Disabled keyword: '{word}'")
            await self._send(
                f"⛔ Trefwoord uitgeschakeld: <code>{word}</code>\n"
                f"Gebruik <code>/add {word}:punten</code> om het weer in te schakelen."
            )
        else:
            await self._send(f"ℹ️ Trefwoord <code>{word}</code> staat al in de uitschakellijst.")

    async def _cmd_threshold(self, args: str) -> None:
        """
        /threshold 8  — Change the minimum score threshold.
        """
        try:
            val = int(args.strip())
            if val < 1 or val > 30:
                raise ValueError()
        except ValueError:
            await self._send(
                "❌ Gebruik: <code>/threshold getal</code> (1–30)\n"
                "Voorbeeld: <code>/threshold 8</code>"
            )
            return

        # Persist to bot_settings.json
        settings = self._load_settings()
        old = settings.get("SCORE_THRESHOLD", os.getenv("SCORE_THRESHOLD", "6"))
        settings["SCORE_THRESHOLD"] = str(val)
        self._save_settings(settings)
        # Apply immediately to environment (affects next FilterEngine init)
        os.environ["SCORE_THRESHOLD"] = str(val)

        logger.info(f"[Bot] Score threshold changed: {old} → {val}")
        await self._send(
            f"🎯 Score drempel aangepast:\n"
            f"  <b>{old}</b> → <b>{val} punten</b>\n\n"
            f"Actief vanaf de volgende scan."
        )

    async def _cmd_startfilter(self, args: str) -> None:
        """
        /startfilter 3   — Set start-date window to 3 months.
        /startfilter 0   — Disable start-date filtering.
        """
        try:
            val = int(args.strip())
            if val < 0 or val > 36:
                raise ValueError()
        except ValueError:
            await self._send(
                "❌ Gebruik: <code>/startfilter maanden</code> (0–36)\n"
                "  <code>/startfilter 3</code> = max 3 maanden vooruit\n"
                "  <code>/startfilter 0</code> = filter uitschakelen"
            )
            return

        settings = self._load_settings()
        old_raw  = settings.get("MAX_START_MONTHS_AHEAD", os.getenv("MAX_START_MONTHS_AHEAD", ""))

        if val == 0:
            settings["MAX_START_MONTHS_AHEAD"] = ""
            os.environ["MAX_START_MONTHS_AHEAD"] = ""
            label = "uitgeschakeld"
        else:
            settings["MAX_START_MONTHS_AHEAD"] = str(val)
            os.environ["MAX_START_MONTHS_AHEAD"] = str(val)
            label = f"{val} maanden vooruit"

        self._save_settings(settings)
        logger.info(f"[Bot] Start date filter: '{old_raw}' → '{label}'")
        await self._send(
            f"📅 Startdatum filter aangepast:\n"
            f"  <b>{label}</b>\n\n"
            f"Actief vanaf de volgende scan."
        )

    async def _cmd_run(self, _args: str) -> None:
        """Trigger an immediate scrape cycle."""
        if self._run_pipeline is None:
            await self._send("❌ Scanfunctie niet beschikbaar.")
            return

        await self._send("🔄 <b>Scan gestart…</b>\nIk stuur je de resultaten zodra ik klaar ben.")
        logger.info("[Bot] Manual scan triggered via Telegram")

        try:
            stats = await self._run_pipeline()
            await self._send(
                f"✅ <b>Scan voltooid!</b>\n\n"
                f"📋 Gescand: {stats.get('scraped', 0)} vacatures\n"
                f"🎯 Gefilterd: {stats.get('passed_filter', 0)} matches\n"
                f"🆕 Nieuw: {stats.get('new_jobs', 0)}\n"
                f"📨 Verstuurd: {stats.get('notified', 0)}\n"
                f"⚠️ Fouten: {stats.get('errors', 0)}"
            )
        except Exception as e:
            logger.error(f"[Bot] Manual scan failed: {e}", exc_info=True)
            await self._send(f"❌ Scan mislukt: {e}")

    # -----------------------------------------------------------------------
    # keywords.json helpers
    # -----------------------------------------------------------------------

    def _load_json(self) -> dict:
        """Load keywords.json, return empty dict on failure."""
        if self.keywords_file.exists():
            try:
                with open(self.keywords_file, encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"[Bot] Failed to read keywords.json: {e}")
        return {}

    def _save_json(self, data: dict) -> None:
        """Save data back to keywords.json with pretty formatting."""
        try:
            with open(self.keywords_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.debug(f"[Bot] keywords.json saved")
        except Exception as e:
            logger.error(f"[Bot] Failed to write keywords.json: {e}")

    # -----------------------------------------------------------------------
    # bot_settings.json helpers (runtime setting persistence)
    # -----------------------------------------------------------------------

    SETTINGS_FILE = Path("bot_settings.json")

    def _load_settings(self) -> dict:
        if self.SETTINGS_FILE.exists():
            try:
                with open(self.SETTINGS_FILE, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_settings(self, data: dict) -> None:
        try:
            with open(self.SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"[Bot] Failed to save bot_settings.json: {e}")


# ---------------------------------------------------------------------------
# Settings loader (called at startup to restore saved settings)
# ---------------------------------------------------------------------------

def apply_saved_settings() -> None:
    """
    Load bot_settings.json and apply any previously saved settings
    to os.environ so they take effect on startup.
    """
    settings_file = Path("bot_settings.json")
    if not settings_file.exists():
        return
    try:
        with open(settings_file, encoding="utf-8") as f:
            settings = json.load(f)
        for key, val in settings.items():
            os.environ[key] = str(val)
            logger.debug(f"[Settings] Restored: {key}={val}")
        logger.info(f"[Settings] Restored {len(settings)} saved settings from bot_settings.json")
    except Exception as e:
        logger.warning(f"[Settings] Failed to load bot_settings.json: {e}")
