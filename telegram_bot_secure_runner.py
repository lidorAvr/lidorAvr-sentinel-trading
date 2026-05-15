import os
import threading
import time
from collections import defaultdict, deque


def _log(msg: str) -> None:
    """Best-effort observability for the security gateway.

    Before this, the secure runner was entirely silent — admin-guard
    rejections, rate-limit trips, and data-source disclosure were
    invisible in `docker logs` (SYSTEM_AUDIT §5.11 / Issue P). Never
    raises; never logs token or admin id. flush=True so the line is
    visible immediately even if PYTHONUNBUFFERED is ever unset.
    """
    try:
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{ts}] [secure_runner] {msg}", flush=True)
    except Exception:
        pass


_HEARTBEAT_DIR = "/app/state"
_HEARTBEAT_INTERVAL = 60


def _touch_heartbeat(name: str) -> None:
    """Write current timestamp to /app/state/{name}_last_cycle so healthchecks can verify liveness."""
    try:
        os.makedirs(_HEARTBEAT_DIR, exist_ok=True)
        path = os.path.join(_HEARTBEAT_DIR, f"{name}_last_cycle")
        with open(path, "w") as fh:
            fh.write(str(time.time()))
    except Exception:
        pass


def _start_heartbeat_thread(name: str, interval: int = _HEARTBEAT_INTERVAL) -> None:
    """Start a daemon thread that touches the heartbeat file every `interval` seconds."""
    def _loop():
        while True:
            _touch_heartbeat(name)
            time.sleep(interval)
    t = threading.Thread(target=_loop, daemon=True, name=f"heartbeat-{name}")
    t.start()

ADMIN_ID = os.getenv('TELEGRAM_ADMIN_ID')
WORKDIR = os.getenv('SENTINEL_WORKDIR', '/home/orangepi/sentinel_trading')
MAX_MESSAGES = int(os.getenv('TELEGRAM_MAX_MESSAGES_PER_WINDOW', '8'))
WINDOW_SECONDS = int(os.getenv('TELEGRAM_RATE_WINDOW_SECONDS', '60'))
COOLDOWN_SECONDS = int(os.getenv('TELEGRAM_RATE_COOLDOWN_SECONDS', '90'))

_events = defaultdict(deque)
_cooldown_until = {}


def guard_decision(chat_id):
    chat_id = str(chat_id)
    now = time.time()
    if not ADMIN_ID or chat_id != str(ADMIN_ID):
        _log(f"REJECT unauthorized — chat_id={chat_id}")
        return False, 'unauthorized'

    until = _cooldown_until.get(chat_id, 0)
    if now < until:
        # In an active cooldown window — not logged per-message on purpose
        # (logging every blocked message would itself be a log flood).
        return False, 'cooldown'
    if until and now >= until:
        _cooldown_until.pop(chat_id, None)
        _events[chat_id].clear()

    events = _events[chat_id]
    while events and now - events[0] > WINDOW_SECONDS:
        events.popleft()
    if len(events) >= MAX_MESSAGES:
        _cooldown_until[chat_id] = now + COOLDOWN_SECONDS
        _log(f"RATE LIMIT tripped — chat_id={chat_id}, "
             f"{MAX_MESSAGES} msgs / {WINDOW_SECONDS}s, "
             f"cooldown {COOLDOWN_SECONDS}s")
        return False, 'rate_limited'
    events.append(now)
    return True, 'ok'


def guard_message(reason):
    if reason == 'unauthorized':
        return '⛔ אין הרשאה להשתמש בבוט הזה.'
    return '⏳ קצב הודעות גבוה מדי. נסה שוב בעוד כמה רגעים.'


def truth_suffix(text):
    if not isinstance(text, str):
        return text
    if 'מקור נתונים:' in text or 'Data source:' in text:
        return text
    markers = ['חדר מצב', 'דו"ח', 'חשיפת תיק', 'Drill-down', 'משטר שוק', 'פוזיציות']
    if any(marker in text for marker in markers):
        _log("data-source disclaimer appended to outgoing report")
        return text + '\n\nℹ️ *מקור נתונים:* Live/Cached לפי זמינות. אם מחיר חי או NAV לא זמינים, יש להתייחס לנתון כהערכה ולאמת מול IBKR לפני פעולה.'
    return text


def install_telegram_hardening():
    import telebot

    original_init = telebot.TeleBot.__init__
    original_message_handler = telebot.TeleBot.message_handler
    original_callback_handler = telebot.TeleBot.callback_query_handler

    def patched_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        raw_send = self.send_message
        raw_edit = self.edit_message_text

        def send_message_guarded(chat_id, text, *a, **kw):
            return raw_send(chat_id, truth_suffix(text), *a, **kw)

        def edit_message_text_guarded(text, chat_id=None, message_id=None, *a, **kw):
            return raw_edit(truth_suffix(text), chat_id, message_id, *a, **kw)

        self.send_message = send_message_guarded
        self.edit_message_text = edit_message_text_guarded

    def guarded_message_handler(self, *dargs, **dkwargs):
        decorator = original_message_handler(self, *dargs, **dkwargs)

        def wrapper(func):
            def guarded(message, *args, **kwargs):
                chat_id = getattr(getattr(message, 'chat', None), 'id', None)
                allowed, reason = guard_decision(chat_id)
                if not allowed:
                    self.send_message(chat_id, guard_message(reason))
                    return None
                return func(message, *args, **kwargs)
            guarded.__name__ = getattr(func, '__name__', 'guarded_message_handler')
            return decorator(guarded)
        return wrapper

    def guarded_callback_handler(self, *dargs, **dkwargs):
        decorator = original_callback_handler(self, *dargs, **dkwargs)

        def wrapper(func):
            def guarded(call, *args, **kwargs):
                chat_id = getattr(getattr(getattr(call, 'message', None), 'chat', None), 'id', None)
                allowed, reason = guard_decision(chat_id)
                if not allowed:
                    try:
                        self.answer_callback_query(call.id)
                    except Exception:
                        pass
                    self.send_message(chat_id, guard_message(reason))
                    return None
                return func(call, *args, **kwargs)
            guarded.__name__ = getattr(func, '__name__', 'guarded_callback_handler')
            return decorator(guarded)
        return wrapper

    telebot.TeleBot.__init__ = patched_init
    telebot.TeleBot.message_handler = guarded_message_handler
    telebot.TeleBot.callback_query_handler = guarded_callback_handler
    _log("telegram hardening installed — admin guard + rate limit + "
         "data-source disclosure active")


def main():
    _log(
        "starting — admin guard "
        f"{'configured' if ADMIN_ID else 'MISSING (all messages will be rejected)'}, "
        f"rate limit {MAX_MESSAGES} msgs / {WINDOW_SECONDS}s, "
        f"cooldown {COOLDOWN_SECONDS}s"
    )
    if os.path.isdir(WORKDIR):
        os.chdir(WORKDIR)
    _start_heartbeat_thread("telegram_bot")
    install_telegram_hardening()
    import telegram_bot
    _log("polling started")
    telegram_bot.bot.infinity_polling()


if __name__ == '__main__':
    main()
