from telegram_guard import TelegramGuard


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def test_guard_blocks_non_admin_users():
    guard = TelegramGuard(admin_id="123", clock=FakeClock())
    decision = guard.check("999")
    assert decision.allowed is False
    assert decision.reason == "unauthorized"


def test_guard_allows_admin_within_limit():
    clock = FakeClock()
    guard = TelegramGuard(admin_id="123", max_messages=2, window_seconds=60, clock=clock)
    assert guard.check("123").allowed is True
    assert guard.check("123").allowed is True


def test_guard_rate_limits_bursts_and_then_recovers_after_cooldown():
    clock = FakeClock()
    guard = TelegramGuard(admin_id="123", max_messages=2, window_seconds=60, cooldown_seconds=30, clock=clock)
    assert guard.check("123").allowed is True
    assert guard.check("123").allowed is True
    blocked = guard.check("123")
    assert blocked.allowed is False
    assert blocked.reason == "rate_limited"
    clock.advance(31)
    assert guard.check("123").allowed is True
