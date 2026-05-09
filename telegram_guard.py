import time
from collections import defaultdict, deque
from dataclasses import dataclass


@dataclass(frozen=True)
class GuardDecision:
    allowed: bool
    reason: str = "ok"
    retry_after_seconds: int = 0


class TelegramGuard:
    """Small in-memory guard for a single-process Telegram bot.

    Goals:
    1. Block non-admin users before any portfolio read/write.
    2. Prevent spam bursts that can hit Telegram/API/provider limits.
    3. Keep the logic deterministic and easy to test.
    """

    def __init__(self, admin_id, max_messages=8, window_seconds=60, cooldown_seconds=90, clock=None):
        self.admin_id = str(admin_id) if admin_id is not None else None
        self.max_messages = int(max_messages)
        self.window_seconds = int(window_seconds)
        self.cooldown_seconds = int(cooldown_seconds)
        self.clock = clock or time.time
        self._events = defaultdict(deque)
        self._cooldown_until = {}

    def check(self, chat_id):
        chat_id = str(chat_id)
        now = float(self.clock())

        if not self.admin_id or chat_id != self.admin_id:
            return GuardDecision(False, "unauthorized")

        cooldown_until = self._cooldown_until.get(chat_id, 0)
        if now < cooldown_until:
            return GuardDecision(False, "cooldown", int(cooldown_until - now))

        events = self._events[chat_id]
        while events and now - events[0] > self.window_seconds:
            events.popleft()

        if len(events) >= self.max_messages:
            self._cooldown_until[chat_id] = now + self.cooldown_seconds
            return GuardDecision(False, "rate_limited", self.cooldown_seconds)

        events.append(now)
        return GuardDecision(True)

    @staticmethod
    def user_message(decision):
        if decision.reason == "unauthorized":
            return "⛔ אין הרשאה להשתמש בבוט הזה."
        if decision.reason in {"rate_limited", "cooldown"}:
            return "⏳ קצב הודעות גבוה מדי. נסה שוב בעוד כמה רגעים."
        return None
