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
        if not self.bot_token:
            logger.warning("[Bot] TELEGRAM_BOT_TOKEN not configured — command handler disabled")
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
        if not self.bot_token:
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

    @property
    def allowed_chat_ids(self) -> list[str]:
        raw = self.chat_id
        return [cid.strip() for cid in raw.split(",") if cid.strip()]

    async def _send(self, text: str, parse_mode: str = "HTML", reply_chat_id: str | None = None) -> None:
        """Send a reply to the specified chat or active chat."""
        target_chat = reply_chat_id or getattr(self, "_active_chat_id", None) or self.chat_id
        # If multiple IDs in self.chat_id, pick the first if target_chat contains comma
        if "," in target_chat:
            target_chat = target_chat.split(",")[0].strip()

        try:
            await self._client.post(
                f"{self._api}/sendMessage",
                json={
                    "chat_id": target_chat,
                    "text": text,
                    "parse_mode": parse_mode,
                    "disable_web_page_preview": True,
                },
                timeout=10,
            )
        except Exception as e:
            logger.warning(f"[Bot] Failed to send reply to chat {target_chat}: {e}")

    # -----------------------------------------------------------------------
    # Update Dispatcher
    # -----------------------------------------------------------------------

    async def _handle_update(self, update: dict) -> None:
        msg = update.get("message", {}) or update.get("channel_post", {})
        text = (msg.get("text") or "").strip()
        chat_id = str(msg.get("chat", {}).get("id", ""))
        chat_type = msg.get("chat", {}).get("type", "private")

        if not text or not chat_id:
            return

        # Security check: allowed if chat_id in TELEGRAM_CHAT_ID list, OR if it's a group chat and ALLOW_GROUPS=true
        allow_all_groups = os.getenv("ALLOW_GROUPS", "true").lower() in ("true", "1", "yes")
        is_allowed = (chat_id in self.allowed_chat_ids) or (allow_all_groups and chat_type in ("group", "supergroup"))

        if not is_allowed:
            logger.debug(f"[Bot] Ignored message from unauthorized chat {chat_id} (type={chat_type})")
            return

        # Store active chat ID so replies go to the exact group/chat that issued the command
        self._active_chat_id = chat_id
        # Automatically register chat_id so notifications dispatch to this chat/group
        self._register_chat_id(chat_id)
        logger.info(f"[Bot] Command received in {chat_type} ({chat_id}): '{text}'")

        # Parse command
        parts  = text.split(None, 1)
        cmd    = parts[0].lower().lstrip("/").split("@")[0]  # strip @botname suffix
        args   = parts[1].strip() if len(parts) > 1 else ""

        handlers = {
            "help":        self._cmd_help,
            "start":       self._cmd_start,   # /start is Telegram's default
            "status":      self._cmd_status,
            "groep":       self._cmd_groep,
            "group":       self._cmd_groep,
            "koppel":      self._cmd_groep,
            "here":        self._cmd_groep,
            "platformen":  self._cmd_platformen,
            "bronnen":     self._cmd_platformen,
            "keywords":    self._cmd_keywords,
            "zoektermen":  self._cmd_zoektermen,
            "termen":      self._cmd_zoektermen,
            "searchterms": self._cmd_zoektermen,
            "add":         self._cmd_add,
            "remove":      self._cmd_remove,
            "disable":     self._cmd_disable,
            "threshold":   self._cmd_threshold,
            "startdatum":  self._cmd_startfilter,
            "startfilter": self._cmd_startfilter,
            "dagoverzicht": self._cmd_dagoverzicht,
            "digest":       self._cmd_dagoverzicht,
            "vandaag":      self._cmd_dagoverzicht,
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

    def _register_chat_id(self, chat_id: str) -> bool:
        """Register a chat_id (e.g. group chat or supergroup) so notification dispatch sends to it."""
        if not chat_id:
            return False

        current_raw = os.getenv("TELEGRAM_CHAT_ID", "")
        current_ids = [c.strip() for c in current_raw.split(",") if c.strip()]

        if chat_id not in current_ids:
            current_ids.append(chat_id)
            new_val = ",".join(current_ids)
            os.environ["TELEGRAM_CHAT_ID"] = new_val
            self._chat_id = new_val

            # Save persistently to bot_settings.json
            settings = self._load_settings()
            settings["TELEGRAM_CHAT_ID"] = new_val
            self._save_settings(settings)
            logger.info(f"[Bot] Auto-registered chat_id '{chat_id}'. Total active chat_ids: {new_val}")
            return True
        return False

    # -----------------------------------------------------------------------
    # Command Implementations
    # -----------------------------------------------------------------------

    async def _cmd_start(self, _args: str) -> None:
        chat_id = getattr(self, "_active_chat_id", self.chat_id)
        self._register_chat_id(chat_id)
        await self._send(
            "⚡ <b>Welkom bij WerkZoeker Bot!</b>\n\n"
            f"✅ <b>Deze chat ({chat_id}) is succesvol gekoppeld!</b>\n"
            "Alle matchende vacatures en opdrachten worden vanaf nu automatisch hier verzonden.\n\n"
            "Gebruik <b>/help</b> voor het overzicht van alle commando's of <b>/run</b> om direct een scan uit te voeren."
        )

    async def _cmd_groep(self, _args: str) -> None:
        chat_id = getattr(self, "_active_chat_id", self.chat_id)
        self._register_chat_id(chat_id)
        active_ids = [c.strip() for c in os.getenv("TELEGRAM_CHAT_ID", "").split(",") if c.strip()]
        await self._send(
            f"👥 <b>Groepsapp Koppeling WerkZoeker</b>\n\n"
            f"📌 <b>Huidige Chat ID:</b> <code>{chat_id}</code>\n"
            f"✅ Deze chat is ingesteld voor het ontvangen van automatische vacaturemeldingen!\n\n"
            f"<b>Actieve gekoppelde chats ({len(active_ids)}):</b>\n"
            f"<code>{', '.join(active_ids)}</code>"
        )

    async def _cmd_help(self, _args: str) -> None:
        await self._send(
            "⚡ <b>WerkZoeker — Commando's</b>\n\n"
            "<b>Informatie & Groepsinstellingen</b>\n"
            "/status — Bot status &amp; statistieken\n"
            "/groep — Koppel deze groepsapp/chat voor meldingen\n"
            "/platformen — Overzicht van alle ondersteunde databronnen\n"
            "/zoektermen — Overzicht van actieve zoektermen &amp; trefwoorden\n"
            "/keywords — Toon alle actieve trefwoorden per score\n\n"
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
            "/dagoverzicht — Dagoverzicht van nieuwe opdrachten (afgelopen 24u)\n"
            "/run — Voer direct een scan uit\n\n"
            f"📂 Trefwoorden bestand: <code>keywords.json</code>"
        )

    async def _cmd_zoektermen(self, _args: str) -> None:
        """Show all active search terms and keywords used by the bot."""
        from filter_engine import load_keywords

        kw = load_keywords(str(self.keywords_file))

        # Group by score points
        by_pts: dict[int, list[str]] = {}
        for word, pts in sorted(kw.items(), key=lambda x: (-x[1], x[0])):
            by_pts.setdefault(pts, []).append(word)

        lines = [
            "🔍 <b>WerkZoeker — Actieve Zoektermen &amp; Trefwoorden</b>\n",
            "<b>🎯 Scraper Zoektermen (waarmee platformen worden doorzocht):</b>",
            "• <code>detail engineer elektrotechniek</code>",
            "• <code>e-engineer zzp / interim</code>",
            "• <code>eplan engineer</code>",
            "• <code>hoogspanning / middenspanning engineer</code>",
            "• <code>werkvoorbereider elektrotechniek</code>\n",
            f"<b>📊 Filter Scoring Trefwoorden ({len(kw)} totaal):</b>",
        ]

        for pts in sorted(by_pts, reverse=True):
            words = by_pts[pts]
            label = f"  <b>+{pts} {'punt' if pts == 1 else 'punten'}</b> ({len(words)}):"
            wordlist = ", ".join(f"<code>{w}</code>" for w in words)
            lines.append(f"{label}\n  {wordlist}\n")

        full_text = "\n".join(lines)
        if len(full_text) > 3900:
            full_text = full_text[:3900] + "\n\n<i>… (zie keywords.json voor het volledige overzicht)</i>"

        await self._send(full_text)

    async def _cmd_platformen(self, _args: str) -> None:
        """Show all supported job platforms dynamically."""
        from main import get_scrapers
        
        # Instantiate scrapers with dummy params to read their SOURCE_NAME
        scrapers = get_scrapers(max_pages=1, rate_limit=0.1, timeout=10)
        source_names = [s.SOURCE_NAME for s in scrapers]
        
        total = len(source_names)
        
        lines = [
            f"🌐 <b>Ondersteunde Databronnen &amp; Platformen</b> ({total} totaal)\n"
        ]
        
        # We limit the output since 50+ lines might exceed telegram single message bounds easily,
        # but 53 sources * ~30 chars is ~1500 chars which is fine.
        for i, name in enumerate(source_names, 1):
            lines.append(f"{i}. <b>{name}</b>")
            
        lines.append(f"\n<i>De bot scant al deze {total} bronnen automatisch en filtert op relevante technische trefwoorden.</i>")
        
        full_text = "\n".join(lines)
        if len(full_text) > 4000:
            full_text = full_text[:4000] + "\n\n<i>… lijst ingekort.</i>"
            
        await self._send(full_text)

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

    async def _cmd_dagoverzicht(self, _args: str) -> None:
        """Show daily overview / digest of jobs found in the last 24 hours."""
        from storage import Storage

        try:
            async with Storage() as db:
                jobs = await db.get_jobs_last_24h()

            if not jobs:
                await self._send(
                    "📅 <b>Dagoverzicht WerkZoeker (Laatste 24 uur)</b>\n\n"
                    "<i>Er zijn in de afgelopen 24 uur geen nieuwe matchende opdrachten/vacatures gevonden.</i>"
                )
                return

            lines = [
                f"📅 <b>Dagoverzicht WerkZoeker — {len(jobs)} Nieuwe Opdrachten (Afgelopen 24u)</b>\n"
            ]

            for idx, j in enumerate(jobs[:15], 1):
                loc = f" 📍 {j['location']}" if j.get("location") else ""
                rate = f" 💰 {j['rate_or_hours']}" if j.get("rate_or_hours") else ""
                lines.append(
                    f"{idx}. <a href=\"{j['url']}\"><b>{j['title']}</b></a>\n"
                    f"   🏢 {j['source']}{loc}{rate} | ⭐ Score: {j['score']}"
                )

            if len(jobs) > 15:
                lines.append(f"\n<i>… en nog {len(jobs) - 15} andere opdrachten in de database.</i>")

            full_msg = "\n".join(lines)
            if len(full_msg) > 3900:
                full_msg = full_msg[:3900] + "\n\n<i>… (lijst ingekort)</i>"

            await self._send(full_msg)

        except Exception as e:
            logger.error(f"[Bot] Failed to generate daily overview: {e}")
            await self._send(f"❌ Fout bij het ophalen van het dagoverzicht: {e}")

    async def _cmd_run(self, _args: str) -> None:
        """Trigger an immediate scrape cycle in background task."""
        if self._run_pipeline is None:
            await self._send("❌ Scanfunctie niet beschikbaar.")
            return

        if getattr(self, "_is_scanning", False):
            await self._send("⚠️ <b>Er draait momenteel al een scan!</b>\nEven geduld a.u.b., je krijgt bericht zodra deze klaar is.")
            return

        self._is_scanning = True
        await self._send("🔄 <b>Scan gestart…</b>\nIk stuur je de resultaten zodra ik klaar ben.")
        logger.info("[Bot] Manual scan triggered via Telegram")

        async def _async_scan():
            try:
                target_chat = getattr(self, "_active_chat_id", None)
                stats = await self._run_pipeline(override_chat_id=target_chat)
                scraped = stats.get('scraped', 0)
                passed = stats.get('passed_filter', 0)
                new_cnt = stats.get('new_jobs', 0)
                notified = stats.get('notified', 0)
                errors = stats.get('errors', 0)
                passed_jobs = stats.get('passed_jobs', [])

                msg_lines = [
                    "✅ <b>Scan voltooid!</b>\n",
                    f"📋 <b>Gescand:</b> {scraped} vacatures",
                    f"🎯 <b>Gefilterd:</b> {passed} matches",
                    f"🆕 <b>Nieuw:</b> {new_cnt}",
                    f"📨 <b>Verstuurd:</b> {notified}",
                    f"⚠️ <b>Fouten:</b> {errors}\n",
                ]

                if passed_jobs:
                    msg_lines.append("<b>🔥 Relevante opdrachten & vacatures (Top matches):</b>")
                    # Sort by score descending
                    sorted_jobs = sorted(passed_jobs, key=lambda x: x[1], reverse=True)
                    for job, score in sorted_jobs[:10]:
                        msg_lines.append(
                            f"• <a href=\"{job.url}\">{job.title}</a>\n"
                            f"  🏢 {job.source} | ⭐ Score: {score}"
                        )
                else:
                    msg_lines.append("<i>Geen matchende vacatures gevonden in deze ronde.</i>")

                full_msg = "\n".join(msg_lines)
                if len(full_msg) > 3900:
                    full_msg = full_msg[:3900] + "\n\n<i>… (lijst ingekort)</i>"

                await self._send(full_msg)
            except Exception as e:
                logger.error(f"[Bot] Manual scan failed: {e}", exc_info=True)
                await self._send(f"❌ Scan mislukt: {e}")
            finally:
                self._is_scanning = False

        asyncio.create_task(_async_scan())

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
            if key == "TELEGRAM_CHAT_ID":
                env_ids = [c.strip() for c in os.getenv("TELEGRAM_CHAT_ID", "").split(",") if c.strip()]
                saved_ids = [c.strip() for c in str(val).split(",") if c.strip()]
                combined = list(dict.fromkeys(env_ids + saved_ids))
                os.environ["TELEGRAM_CHAT_ID"] = ",".join(combined)
            else:
                os.environ[key] = str(val)
            logger.debug(f"[Settings] Restored: {key}={os.environ.get(key)}")
        logger.info(f"[Settings] Restored {len(settings)} saved settings from bot_settings.json")
    except Exception as e:
        logger.warning(f"[Settings] Failed to load bot_settings.json: {e}")
