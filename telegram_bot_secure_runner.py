import os
import time
from collections import defaultdict, deque

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
        return False, 'unauthorized'

    until = _cooldown_until.get(chat_id, 0)
    if now < until:
        return False, 'cooldown'
    if until and now >= until:
        _cooldown_until.pop(chat_id, None)
        _events[chat_id].clear()

    events = _events[chat_id]
    while events and now - events[0] > WINDOW_SECONDS:
        events.popleft()
    if len(events) >= MAX_MESSAGES:
        _cooldown_until[chat_id] = now + COOLDOWN_SECONDS
        return False, 'rate_limited'
    events.append(now)
    return True, 'ok'


def guard_message(reason):
    if reason == 'unauthorized':
        return 'Access denied.'
    return 'Rate limit reached. Try again later.'


def truth_suffix(text):
    if not isinstance(text, str):
        return text
    if 'Data source:' in text:
        return text
    markers = ['portfolio', 'risk', 'Drill-down', 'market regime']
    if any(marker in text for marker in markers):
        return text + '\n\nData source: Live/Cached by availability. Treat fallback values as estimates before trading action.'
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


def main():
    if os.path.isdir(WORKDIR):
        os.chdir(WORKDIR)
    install_telegram_hardening()
    import telegram_bot
    telegram_bot.bot.infinity_polling()


if __name__ == '__main__':
    main()
