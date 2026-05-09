import builtins
import os
import time
from collections import defaultdict, deque

ADMIN_ID = os.getenv('TELEGRAM_ADMIN_ID')
CONFIG_PATH = os.getenv('SENTINEL_CONFIG_PATH', '/app/sentinel_config.json')

_original_open = builtins.open


def _safe_open(file, *args, **kwargs):
    if isinstance(file, (str, bytes, os.PathLike)) and str(file) == 'sentinel_config.json':
        file = CONFIG_PATH
    return _original_open(file, *args, **kwargs)


builtins.open = _safe_open

_events = defaultdict(deque)
_cooldown_until = {}


def _guard_decision(chat_id, max_messages=8, window_seconds=60, cooldown_seconds=90):
    chat_id = str(chat_id)
    now = time.time()

    if not ADMIN_ID or chat_id != str(ADMIN_ID):
        return False, 'unauthorized', 0

    until = _cooldown_until.get(chat_id, 0)
    if now < until:
        return False, 'cooldown', int(until - now)
    if until and now >= until:
        _cooldown_until.pop(chat_id, None)
        _events[chat_id].clear()

    events = _events[chat_id]
    while events and now - events[0] > window_seconds:
        events.popleft()

    if len(events) >= max_messages:
        _cooldown_until[chat_id] = now + cooldown_seconds
        return False, 'rate_limited', cooldown_seconds

    events.append(now)
    return True, 'ok', 0


def _guard_message(reason):
    if reason == 'unauthorized':
        return '⛔ אין הרשאה להשתמש בבוט הזה.'
    return '⏳ קצב הודעות גבוה מדי. נסה שוב בעוד כמה רגעים.'


def _truth_suffix(text):
    if not isinstance(text, str):
        return text
    if 'מקור נתונים:' in text or 'מקור NAV:' in text:
        return text
    report_markers = ['חדר מצב', 'דו"ח', 'חשיפת תיק', 'Drill-down', 'משטר שוק']
    if any(marker in text for marker in report_markers):
        return text + '\n\nℹ️ *מקור נתונים:* Live/Cached לפי זמינות. אם מחיר חי או NAV לא זמינים, הנתון מסומן כהערכה/משוער ויש לאמת מול IBKR לפני פעולה.'
    return text


def _patch_telebot():
    try:
        import telebot
    except Exception:
        return

    original_init = telebot.TeleBot.__init__

    def patched_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)

        raw_send = self.send_message
        raw_edit = self.edit_message_text

        def send_message_guarded(chat_id, text, *a, **kw):
            text = _truth_suffix(text)
            return raw_send(chat_id, text, *a, **kw)

        def edit_message_text_guarded(text, chat_id=None, message_id=None, *a, **kw):
            text = _truth_suffix(text)
            return raw_edit(text, chat_id, message_id, *a, **kw)

        self.send_message = send_message_guarded
        self.edit_message_text = edit_message_text_guarded

    telebot.TeleBot.__init__ = patched_init

    original_message_handler = telebot.TeleBot.message_handler
    original_callback_handler = telebot.TeleBot.callback_query_handler

    def guarded_message_handler(self, *dargs, **dkwargs):
        decorator = original_message_handler(self, *dargs, **dkwargs)

        def wrapper(func):
            def guarded(message, *args, **kwargs):
                chat_id = getattr(getattr(message, 'chat', None), 'id', None)
                allowed, reason, _ = _guard_decision(chat_id)
                if not allowed:
                    self.send_message(chat_id, _guard_message(reason))
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
                allowed, reason, _ = _guard_decision(chat_id)
                if not allowed:
                    try:
                        self.answer_callback_query(call.id)
                    except Exception:
                        pass
                    self.send_message(chat_id, _guard_message(reason))
                    return None
                return func(call, *args, **kwargs)

            guarded.__name__ = getattr(func, '__name__', 'guarded_callback_handler')
            return decorator(guarded)

        return wrapper

    telebot.TeleBot.message_handler = guarded_message_handler
    telebot.TeleBot.callback_query_handler = guarded_callback_handler


_patch_telebot()
