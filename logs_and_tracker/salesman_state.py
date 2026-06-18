"""
salesman_state.py — AMTCE Intelligent Salesman State Engine
============================================================
Tracks harvest and publish activity across process restarts so that
missed schedule slots are detected and recovered automatically.

Think of it like a sales rep with a daily quota:
  - Knows exactly which harvest runs fired and which didn't
  - Knows which publish slots were served and which were missed
  - Plans catch-up work intelligently (spread out, not all-at-once)
  - Persists Apify quota to disk so restarts don't reset the budget

State file: Intelligence_Data/salesman_state.json
"""

import os
import json
import time
import logging
import threading
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Tuple

logger = logging.getLogger(__name__)

# ── State file location ──────────────────────────────────────────────────────
_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(_MODULE_DIR)
_STATE_DIR  = os.path.abspath(os.path.join(PROJECT_ROOT, "Intelligence_Data"))
_STATE_FILE = os.path.join(_STATE_DIR, "salesman_state.json")
_LOCK       = threading.Lock()

os.makedirs(_STATE_DIR, exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# Raw I/O helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load_state() -> Dict:
    """Load state from disk. Returns a safe default if missing or corrupt."""
    if not os.path.exists(_STATE_FILE):
        return _default_state()
    try:
        with open(_STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Ensure all keys exist (forward-compat for new fields)
        default = _default_state()
        for section in ("harvest", "publisher", "apify", "scraped_posts", "account_scrape_throttle"):
            if section not in data:
                data[section] = default[section]
            else:
                for k, v in default[section].items():
                    data[section].setdefault(k, v)
        return data
    except Exception as exc:
        logger.warning("⚠️ [SALESMAN] State file corrupt, resetting: %s", exc)
        return _default_state()


def _save_state(state: Dict) -> None:
    """Atomically save state to disk."""
    try:
        tmp = _STATE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        os.replace(tmp, _STATE_FILE)
    except Exception as exc:
        logger.error("❌ [SALESMAN] Failed to save state: %s", exc)


def _default_state() -> Dict:
    today = _today_str()
    return {
        "harvest": {
            "last_run_date":            today,
            "slots_completed_today":    [],
            "catchup_fired_today":      False,
            "total_runs_all_time":      0,
        },
        "publisher": {
            "last_check_date":          today,
            "slots_published_today":    [],
            "slots_missed_today":       [],
            "catchup_slots_today":      None,
            "deficit_videos":           0,
        },
        "apify": {
            "quota_date":               today,
            "quota_used":               0,
            "quota_limit":              int(os.getenv("APIFY_DAILY_QUOTA", "50")),
            "total_calls_all_time":     0,
        },
        "scraped_posts": {
            "shortcodes":               [],
            "total_seen":               0,
        },
        "account_scrape_throttle": {
            # Maps username -> ISO timestamp of last scrape (e.g. "nora_fatehi": "2026-05-26T09:00:00")
            "last_scraped_at":          {},
        },
    }


def _today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _parse_hhmm(t: str) -> Tuple[int, int]:
    h, _, m = t.strip().partition(":")
    return int(h), int(m or "0")


# ─────────────────────────────────────────────────────────────────────────────
# Public API — Harvest
# ─────────────────────────────────────────────────────────────────────────────

class HarvestState:
    """
    Manages harvest slot tracking and catch-up logic.

    Usage:
        state = HarvestState()
        if state.should_catchup():
            run_daily_cycle()
        ...
        state.mark_slot_complete("01:45")
    """

    def __init__(self):
        with _LOCK:
            self._state = _load_state()
            self._roll_date_if_new_day()

    def _roll_date_if_new_day(self):
        """Reset daily counters when a new day starts."""
        today = _today_str()
        h = self._state["harvest"]
        if h["last_run_date"] != today:
            logger.info("🌅 [HARVEST SALESMAN] New day detected — rolling counters")
            h["last_run_date"]         = today
            h["slots_completed_today"] = []
            h["catchup_fired_today"]   = False
            _save_state(self._state)

    def slots_completed_today(self) -> List[str]:
        with _LOCK:
            self._state = _load_state()
            self._roll_date_if_new_day()
            return list(self._state["harvest"]["slots_completed_today"])

    def mark_slot_complete(self, slot_hhmm: str) -> None:
        """Call this immediately after a successful harvest run."""
        with _LOCK:
            state = _load_state()
            h = state["harvest"]
            today = _today_str()
            if h["last_run_date"] != today:
                h["last_run_date"]         = today
                h["slots_completed_today"] = []
                h["catchup_fired_today"]   = False
            if slot_hhmm not in h["slots_completed_today"]:
                h["slots_completed_today"].append(slot_hhmm)
            h["total_runs_all_time"] = h.get("total_runs_all_time", 0) + 1
            _save_state(state)
            logger.info("✅ [HARVEST SALESMAN] Slot marked complete: %s", slot_hhmm)

    def mark_catchup_fired(self) -> None:
        with _LOCK:
            state = _load_state()
            state["harvest"]["catchup_fired_today"] = True
            _save_state(state)

    def should_catchup(self, configured_slots: List[str]) -> bool:
        """
        Returns True if:
          - At least one configured harvest slot passed today
          - AND none of those passed slots are in slots_completed_today
          - AND no catch-up has fired yet today
          - AND the program is running (obviously)

        Max 1 catch-up per day — we don't cascade multi-day deficits
        into multiple back-to-back Apify calls.
        """
        with _LOCK:
            self._state = _load_state()
            self._roll_date_if_new_day()
            h = self._state["harvest"]

        if h["catchup_fired_today"]:
            return False

        now = datetime.now()
        missed_any = False
        for slot_str in configured_slots:
            try:
                hh, mm = _parse_hhmm(slot_str)
            except Exception:
                continue
            slot_dt = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
            if slot_dt < now and slot_str not in h["slots_completed_today"]:
                missed_any = True
                break

        if missed_any:
            logger.warning(
                "🚨 [HARVEST SALESMAN] Missed harvest slot(s) detected. "
                "Completed today: %s | Configured: %s",
                h["slots_completed_today"], configured_slots
            )
        return missed_any

    def get_summary(self) -> str:
        with _LOCK:
            h = _load_state()["harvest"]
        return (
            f"Harvest State — {h['last_run_date']} | "
            f"Done: {h['slots_completed_today']} | "
            f"Catchup fired: {h['catchup_fired_today']} | "
            f"Total runs: {h['total_runs_all_time']}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Public API — Publisher
# ─────────────────────────────────────────────────────────────────────────────

class PublisherState:
    """
    Manages publish slot tracking and intelligent catch-up scheduling.

    The publisher calls:
        state = PublisherState()
        catchup_slots = state.get_catchup_slots(configured_slots)
        # → returns extra publish times to fire today to make up for misses
        state.mark_slot_published("07:30")
        state.mark_slot_missed("04:02")
    """

    # Max number of catch-up videos to schedule in one day
    MAX_CATCHUP_PER_DAY: int = int(os.getenv("PUBLISHER_MAX_CATCHUP_PER_DAY", "2"))

    def __init__(self):
        with _LOCK:
            self._state = _load_state()
            self._roll_date_if_new_day()

    def _roll_date_if_new_day(self):
        today = _today_str()
        p = self._state["publisher"]
        if p["last_check_date"] != today:
            logger.info("🌅 [PUBLISHER SALESMAN] New day detected — rolling counters")
            # Carry over deficit from yesterday (capped at MAX_CATCHUP_PER_DAY)
            yesterday_deficit = min(
                len(p.get("slots_missed_today", [])),
                self.MAX_CATCHUP_PER_DAY
            )
            p["last_check_date"]       = today
            p["slots_published_today"] = []
            p["slots_missed_today"]    = []
            p["catchup_slots_today"]   = None
            p["deficit_videos"]        = yesterday_deficit
            if yesterday_deficit:
                logger.warning(
                    "📊 [PUBLISHER SALESMAN] Carrying %d deficit video(s) from yesterday",
                    yesterday_deficit
                )
            _save_state(self._state)

    def mark_slot_published(self, slot_hhmm: str) -> None:
        """Call this when a publish slot successfully fires."""
        with _LOCK:
            state = _load_state()
            p = state["publisher"]
            if slot_hhmm not in p["slots_published_today"]:
                p["slots_published_today"].append(slot_hhmm)
            # Clear from missed if it was wrongly tracked
            if slot_hhmm in p["slots_missed_today"]:
                p["slots_missed_today"].remove(slot_hhmm)
            # Reduce deficit
            if p["deficit_videos"] > 0:
                p["deficit_videos"] -= 1
            _save_state(state)
            logger.info("✅ [PUBLISHER SALESMAN] Slot published: %s", slot_hhmm)

    def mark_slot_missed(self, slot_hhmm: str) -> None:
        """Call this when a slot is detected as missed (program was off)."""
        with _LOCK:
            state = _load_state()
            p = state["publisher"]
            if slot_hhmm not in p["slots_missed_today"] and slot_hhmm not in p["slots_published_today"]:
                p["slots_missed_today"].append(slot_hhmm)
                p["deficit_videos"] = p.get("deficit_videos", 0) + 1
                logger.warning("⚠️ [PUBLISHER SALESMAN] Missed slot recorded: %s", slot_hhmm)
            _save_state(state)

    def get_missed_slots(self, configured_slots: List[str]) -> List[str]:
        """
        Compare configured slots against published-today to find what was missed.
        Only considers slots that have already passed.
        """
        now = datetime.now()
        with _LOCK:
            state = _load_state()
        p = state["publisher"]
        today = _today_str()

        if p["last_check_date"] != today:
            return []

        missed = []
        for slot_str in configured_slots:
            try:
                hh, mm = _parse_hhmm(slot_str)
            except Exception:
                continue
            slot_dt = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
            # Slot must have passed (at least PROCESS_LEAD_TIME_MINUTES ago)
            lead = int(os.getenv("PROCESS_LEAD_TIME_MINUTES", "6"))
            fire_dt = slot_dt - timedelta(minutes=lead)
            if fire_dt < now and slot_str not in p["slots_published_today"]:
                missed.append(slot_str)
        return missed

    def plan_catchup_slots(
        self,
        configured_slots: List[str],
        active_start: str = "07:00",
        active_end: str = "23:00",
    ) -> List[str]:
        """
        Intelligently plans catch-up publish times for missed slots.

        Strategy:
          - Find gaps between remaining static slots and now
          - Insert catch-up times at the MIDPOINT of each gap
          - Respect active hours (no overnight catch-up)
          - Cap at MAX_CATCHUP_PER_DAY total

        Returns a list of HH:MM strings (new virtual slots to fire today).
        """
        with _LOCK:
            state = _load_state()
        p = state["publisher"]

        # Don't re-plan if already planned today
        if p.get("catchup_slots_today") is not None:
            return list(p["catchup_slots_today"])

        missed = self.get_missed_slots(configured_slots)
        if not missed:
            return []

        now = datetime.now()
        try:
            sh, sm = _parse_hhmm(active_start)
            eh, em = _parse_hhmm(active_end)
        except Exception:
            sh, sm = 7, 0
            eh, em = 23, 0

        active_start_dt = now.replace(hour=sh, minute=sm, second=0, microsecond=0)
        active_end_dt   = now.replace(hour=eh, minute=em, second=0, microsecond=0)

        # Find future static slot times
        future_slots = []
        for slot_str in configured_slots:
            try:
                hh, mm = _parse_hhmm(slot_str)
            except Exception:
                continue
            slot_dt = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
            if slot_dt > now:
                future_slots.append(slot_dt)
        future_slots.sort()

        catchup_times = []
        anchor = max(now + timedelta(minutes=15), active_start_dt)  # at least 15min from now

        for i, _ in enumerate(missed):
            if len(catchup_times) >= self.MAX_CATCHUP_PER_DAY:
                break

            if future_slots:
                # Midpoint between now/anchor and next static slot
                next_static = future_slots[0]
                gap_mid = anchor + (next_static - anchor) / 2
                # Round to nearest 5 minutes
                gap_mid = gap_mid.replace(
                    minute=(gap_mid.minute // 5) * 5, second=0, microsecond=0
                )
            else:
                # No future static slot — space catch-ups 60 min apart within active hours
                gap_mid = anchor + timedelta(hours=1)

            # Only add if within active hours
            if active_start_dt <= gap_mid <= active_end_dt and gap_mid > now:
                slot_str = gap_mid.strftime("%H:%M")
                if slot_str not in catchup_times:
                    catchup_times.append(slot_str)
                    logger.info(
                        "📅 [PUBLISHER SALESMAN] Catch-up slot planned: %s (missed: %s)",
                        slot_str, missed[i]
                    )
                anchor = gap_mid + timedelta(minutes=30)  # min spacing
            else:
                if gap_mid > active_end_dt:
                    logger.info(
                        "⏭️ [PUBLISHER SALESMAN] Catch-up slot %s outside active hours — stopping planning",
                        gap_mid.strftime("%H:%M")
                    )
                    break
                logger.info(
                    "⏭️ [PUBLISHER SALESMAN] Catch-up slot %s outside active hours — skipped",
                    gap_mid.strftime("%H:%M")
                )

        # Persist the plan
        with _LOCK:
            state = _load_state()
            state["publisher"]["catchup_slots_today"] = catchup_times
            _save_state(state)

        if catchup_times:
            logger.info(
                "📊 [PUBLISHER SALESMAN] Catch-up plan: %d missed → publishing at %s",
                len(missed), catchup_times
            )
        return catchup_times

    def get_deficit(self) -> int:
        with _LOCK:
            return _load_state()["publisher"].get("deficit_videos", 0)

    def get_summary(self) -> str:
        with _LOCK:
            p = _load_state()["publisher"]
        return (
            f"Publisher State — {p['last_check_date']} | "
            f"Published: {p['slots_published_today']} | "
            f"Missed: {p['slots_missed_today']} | "
            f"Catch-up: {p['catchup_slots_today']} | "
            f"Deficit: {p['deficit_videos']}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Public API — Apify Persistent Quota
# ─────────────────────────────────────────────────────────────────────────────

class ApifyQuotaState:
    """
    Disk-persisted Apify quota tracker.
    Survives process restarts — critical for a $5/month budget.

    Replaces the in-memory _quota_used / _quota_date in apify_downloader.py.
    """

    def __init__(self):
        with _LOCK:
            state = _load_state()
            a = state["apify"]
            today = _today_str()
            if a["quota_date"] != today:
                logger.info("📅 [APIFY SALESMAN] New day — resetting Apify quota")
                a["quota_date"]  = today
                a["quota_used"]  = 0
                a["quota_limit"] = int(os.getenv("APIFY_DAILY_QUOTA", "50"))
                _save_state(state)

    def check(self, needed: int = 1) -> bool:
        """Returns True if quota allows `needed` more calls."""
        with _LOCK:
            state = _load_state()
            a = state["apify"]
            today = _today_str()
            if a["quota_date"] != today:
                a["quota_date"] = today
                a["quota_used"] = 0
                _save_state(state)
            used  = a.get("quota_used", 0)
            limit = a.get("quota_limit", int(os.getenv("APIFY_DAILY_QUOTA", "50")))

        if used + needed > limit:
            logger.warning(
                "🛑 [APIFY SALESMAN] Disk quota exhausted (%d/%d). "
                "Protecting the $5 budget. 💰",
                used, limit
            )
            return False
        return True

    def consume(self, amount: int = 1) -> None:
        """Record that `amount` Apify calls were made."""
        with _LOCK:
            state = _load_state()
            a = state["apify"]
            today = _today_str()
            if a["quota_date"] != today:
                a["quota_date"] = today
                a["quota_used"] = 0
            a["quota_used"]           = a.get("quota_used", 0) + amount
            a["total_calls_all_time"] = a.get("total_calls_all_time", 0) + amount
            _save_state(state)
            logger.info(
                "💰 [APIFY SALESMAN] Quota used: %d/%d today | %d all-time",
                a["quota_used"], a.get("quota_limit", 50), a["total_calls_all_time"]
            )

    def remaining(self) -> int:
        with _LOCK:
            a = _load_state()["apify"]
            today = _today_str()
            if a["quota_date"] != today:
                return int(os.getenv("APIFY_DAILY_QUOTA", "50"))
            return max(0, a.get("quota_limit", 50) - a.get("quota_used", 0))

    def get_summary(self) -> str:
        with _LOCK:
            a = _load_state()["apify"]
        return (
            f"Apify Quota — {a['quota_date']} | "
            f"Used: {a.get('quota_used', 0)}/{a.get('quota_limit', 50)} | "
            f"Remaining: {self.remaining()} | "
            f"Total all-time: {a.get('total_calls_all_time', 0)}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Convenience singletons (lazy init on first import)
# ─────────────────────────────────────────────────────────────────────────────

_harvest_state:   Optional[HarvestState]   = None
_publisher_state: Optional[PublisherState] = None
_apify_quota:     Optional[ApifyQuotaState] = None
_scraped_posts:   Optional["ScrapedPostsRegistry"] = None
_singleton_lock   = threading.Lock()


# ─────────────────────────────────────────────────────────────────────────────
# Public API — Scraped Posts Registry (Deduplication)
# ─────────────────────────────────────────────────────────────────────────────

class ScrapedPostsRegistry:
    """
    Disk-persisted registry of all Instagram post shortcodes that have
    already been scraped/downloaded. Prevents Apify from re-downloading
    and re-uploading the exact same posts across harvest cycles.

    Usage in apify_downloader.py:
        from salesman_state import get_scraped_posts_registry
        registry = get_scraped_posts_registry()
        new_items = registry.filter_new(items)   # removes already-seen posts
        registry.mark_seen([item["shortcode"] for item in new_items])
    """

    # Maximum number of shortcodes to retain (rolling window to prevent
    # unbounded state file growth). Oldest entries are pruned first.
    MAX_SHORTCODES: int = int(os.getenv("SCRAPED_POSTS_MAX_HISTORY", "5000"))

    def _get_shortcodes_set(self) -> set:
        with _LOCK:
            state = _load_state()
            return set(state.get("scraped_posts", {}).get("shortcodes", []))

    def is_seen(self, shortcode: str) -> bool:
        """Returns True if this shortcode was already processed."""
        if not shortcode:
            return False
        return shortcode in self._get_shortcodes_set()

    def filter_new(self, items: List[Dict]) -> List[Dict]:
        """
        Filters a list of Apify result dicts, returning only posts whose
        shortcode has NOT been seen before. Logs how many were dropped.
        """
        seen = self._get_shortcodes_set()
        new_items = []
        skipped = 0
        for item in items:
            sc = item.get("shortcode", "")
            if sc and sc in seen:
                skipped += 1
                logger.info(
                    "⏭️ [DEDUP] Skipping already-scraped post: shortcode=%s @%s",
                    sc, item.get("ownerUsername", "?")
                )
            else:
                new_items.append(item)

        if skipped:
            logger.info(
                "🔁 [DEDUP] %d/%d posts were duplicates — %d new posts passed through",
                skipped, len(items), len(new_items)
            )
        else:
            logger.info("✅ [DEDUP] All %d posts are new (no duplicates)", len(items))
        return new_items

    def mark_seen(self, shortcodes: List[str]) -> None:
        """
        Persists the given shortcodes to the registry so future
        harvest cycles will skip them.
        """
        if not shortcodes:
            return
        valid = [sc for sc in shortcodes if sc]
        if not valid:
            return
        with _LOCK:
            state = _load_state()
            sp = state.setdefault("scraped_posts", {"shortcodes": [], "total_seen": 0})
            existing = sp.get("shortcodes", [])
            # Merge (preserve order, no duplicates)
            existing_set = set(existing)
            added = [sc for sc in valid if sc not in existing_set]
            combined = existing + added
            # Rolling-window pruning: drop the oldest entries if over cap
            if len(combined) > self.MAX_SHORTCODES:
                combined = combined[-self.MAX_SHORTCODES:]
            sp["shortcodes"]  = combined
            sp["total_seen"]  = sp.get("total_seen", 0) + len(added)
            _save_state(state)
        logger.info(
            "💾 [DEDUP] Marked %d new shortcodes as seen (total ever: %d)",
            len(added), sp["total_seen"]
        )

    def get_summary(self) -> str:
        with _LOCK:
            sp = _load_state().get("scraped_posts", {})
        return (
            f"Scraped Posts Registry | "
            f"In memory: {len(sp.get('shortcodes', []))} | "
            f"Total ever: {sp.get('total_seen', 0)}"
        )



def get_harvest_state() -> HarvestState:
    global _harvest_state
    with _singleton_lock:
        if _harvest_state is None:
            _harvest_state = HarvestState()
    return _harvest_state


def get_publisher_state() -> PublisherState:
    global _publisher_state
    with _singleton_lock:
        if _publisher_state is None:
            _publisher_state = PublisherState()
    return _publisher_state


def get_apify_quota() -> ApifyQuotaState:
    global _apify_quota
    with _singleton_lock:
        if _apify_quota is None:
            _apify_quota = ApifyQuotaState()
    return _apify_quota


def get_scraped_posts_registry() -> ScrapedPostsRegistry:
    global _scraped_posts
    with _singleton_lock:
        if _scraped_posts is None:
            _scraped_posts = ScrapedPostsRegistry()
    return _scraped_posts


# ─────────────────────────────────────────────────────────────────────────────
# Public API — Per-Account Scrape Cooldown (24h throttle)
# ─────────────────────────────────────────────────────────────────────────────

class AccountScrapeThrottle:
    """
    Disk-persisted per-account 24h scrape cooldown.
    Prevents scraping the same Instagram account more than once per day.

    Usage in apify_downloader.py:
        from salesman_state import get_account_scrape_throttle
        throttle = get_account_scrape_throttle()
        ready, blocked = throttle.filter_ready(source_accounts)
        # ready   = accounts that can be scraped now
        # blocked = accounts that were scraped in the last 24h
        throttle.mark_scraped(ready)
    """

    COOLDOWN_HOURS: int = int(os.getenv("APIFY_ACCOUNT_COOLDOWN_HOURS", "24"))

    def _get_last_scraped(self) -> Dict[str, str]:
        with _LOCK:
            state = _load_state()
            return dict(state.get("account_scrape_throttle", {}).get("last_scraped_at", {}))

    def is_ready(self, username: str) -> bool:
        """Returns True if the account is eligible for scraping (cooldown expired)."""
        username = username.lstrip("@")
        last_scraped = self._get_last_scraped()
        if username not in last_scraped:
            return True
        try:
            last_ts = datetime.fromisoformat(last_scraped[username])
            age_hours = (datetime.now() - last_ts).total_seconds() / 3600
            return age_hours >= self.COOLDOWN_HOURS
        except Exception:
            return True  # corrupt timestamp — allow it

    def filter_ready(self, accounts: List[str]) -> tuple:
        """
        Splits accounts into (ready, blocked) lists.
        ready   = accounts whose 24h cooldown has expired — safe to scrape
        blocked = accounts scraped within the last 24h — skip them
        """
        last_scraped = self._get_last_scraped()
        ready, blocked = [], []
        for acc in accounts:
            clean = acc.lstrip("@")
            if clean not in last_scraped:
                ready.append(acc)
                continue
            try:
                last_ts = datetime.fromisoformat(last_scraped[clean])
                age_hours = (datetime.now() - last_ts).total_seconds() / 3600
                if age_hours >= self.COOLDOWN_HOURS:
                    ready.append(acc)
                else:
                    blocked.append(acc)
                    logger.info(
                        "⏳ [ACCOUNT_THROTTLE] @%s blocked — scraped %.1fh ago (cooldown=%dh)",
                        clean, age_hours, self.COOLDOWN_HOURS
                    )
            except Exception:
                ready.append(acc)  # corrupt timestamp — allow

        if blocked:
            logger.info(
                "🚧 [ACCOUNT_THROTTLE] %d/%d accounts on cooldown: %s",
                len(blocked), len(accounts),
                [a.lstrip('@') for a in blocked]
            )
        logger.info(
            "✅ [ACCOUNT_THROTTLE] %d/%d accounts ready to scrape",
            len(ready), len(accounts)
        )
        return ready, blocked

    def mark_scraped(self, accounts: List[str]) -> None:
        """Record the current time as the last-scraped timestamp for each account."""
        if not accounts:
            return
        now_iso = datetime.now().isoformat()
        with _LOCK:
            state = _load_state()
            throttle = state.setdefault(
                "account_scrape_throttle", {"last_scraped_at": {}}
            )
            ts_map = throttle.setdefault("last_scraped_at", {})
            for acc in accounts:
                clean = acc.lstrip("@")
                ts_map[clean] = now_iso
            _save_state(state)
        logger.info(
            "💾 [ACCOUNT_THROTTLE] Marked %d accounts as scraped at %s",
            len(accounts), now_iso
        )

    def get_summary(self) -> str:
        last_scraped = self._get_last_scraped()
        return (
            f"Account Throttle | "
            f"Tracked accounts: {len(last_scraped)} | "
            f"Cooldown: {self.COOLDOWN_HOURS}h"
        )


_account_throttle: Optional["AccountScrapeThrottle"] = None


def get_account_scrape_throttle() -> AccountScrapeThrottle:
    global _account_throttle
    with _singleton_lock:
        if _account_throttle is None:
            _account_throttle = AccountScrapeThrottle()
    return _account_throttle


def log_full_status() -> None:
    """Dump a full salesman dashboard to the logger."""
    logger.info("=" * 60)
    logger.info("🧠 SALESMAN STATE DASHBOARD")
    logger.info("  %s", get_harvest_state().get_summary())
    logger.info("  %s", get_publisher_state().get_summary())
    logger.info("  %s", get_apify_quota().get_summary())
    logger.info("  %s", get_scraped_posts_registry().get_summary())
    logger.info("  %s", get_account_scrape_throttle().get_summary())
    logger.info("=" * 60)
