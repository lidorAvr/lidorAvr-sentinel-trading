"""
Telegram menu and keyboard builders for Sentinel Trading.

No bot, supabase, or user_state dependencies — safe to import anywhere.
"""
import telebot

_SETUPS = ["VCP", "ALGO", "SWING", "EP"]


def get_main_menu():
    """תפריט ראשי — 5 קטגוריות."""
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(telebot.types.KeyboardButton("📊 מצב תיק"), telebot.types.KeyboardButton("🔬 ניתוח"))
    markup.add(telebot.types.KeyboardButton("📚 יומן"), telebot.types.KeyboardButton("❓ עזרה"))
    markup.add(telebot.types.KeyboardButton("🛠️ מפתח"))
    return markup


def get_developer_menu():
    """תפריט מפתח — כלי פיתוח ודיבאג."""
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(telebot.types.KeyboardButton("📡 IBKR Sync ידני"), telebot.types.KeyboardButton("📤 העלה דוח XML"))
    markup.add(telebot.types.KeyboardButton("🔄 Git Pull + Deploy"), telebot.types.KeyboardButton("⚙️ הצג Config"))
    markup.add(telebot.types.KeyboardButton("📊 תוצאת Sync אחרון"), telebot.types.KeyboardButton("🏥 בריאות מערכת"))
    # Sprint-17 Scope item B — on-demand report for the LAST COMPLETE period
    # (developer/testing only; admin-gated via the existing dev-menu/PIN path).
    # Reuses the scheduler period logic + render/deliver path; NEVER mutates
    # the real snapshot store or the scheduler period-dedup.
    markup.add(telebot.types.KeyboardButton("📈 דוח שבועי עכשיו"), telebot.types.KeyboardButton("📆 דוח חודשי עכשיו"))
    # Sprint-21 WS-A — live PURE READ-ONLY data-delivery probe (developer/
    # testing only; admin-gated via the SAME existing dev-menu/PIN path).
    # Re-runs the exact scheduler fetch read-only; NEVER writes/snap_save/
    # mutates state and NEVER prints secrets (MARK_SPRINT21_RULINGS §WS-A).
    markup.add(telebot.types.KeyboardButton("🔬 בדיקת נתוני תקופה (Probe)"))
    markup.add(telebot.types.KeyboardButton("📋 לוגים"), telebot.types.KeyboardButton("⬅️ חזרה לתפריט ראשי"))
    return markup


def get_portfolio_menu():
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    markup.add(telebot.types.KeyboardButton("📊 חדר מצב (פוזיציות)"))
    markup.add(telebot.types.KeyboardButton("📋 משימות פתוחות"))
    markup.add(telebot.types.KeyboardButton("🎯 קידום סטופ"))
    markup.add(telebot.types.KeyboardButton("🌡️ משטר שוק וסיכונים"))
    # #9 / DEC-20260515-008 — user-facing audit review. NORMAL user menu
    # (a first-class self-review need, not dev/forensic); NEVER in
    # get_developer_menu(). Last action row, directly above "back to main".
    markup.add(telebot.types.KeyboardButton("🧾 הפעולות שלי"))
    markup.add(telebot.types.KeyboardButton("⬅️ חזרה לתפריט ראשי"))
    return markup


def get_analysis_menu():
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    markup.add(telebot.types.KeyboardButton("🔬 סקירת מניה"))
    markup.add(telebot.types.KeyboardButton("🧠 ניתוח מינרביני מלא"))
    markup.add(telebot.types.KeyboardButton("⬅️ חזרה לתפריט ראשי"))
    return markup


def get_journal_menu():
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    # Label is intentionally explicit: this is a SEQUENTIAL "next missing
    # field" walker, not a browsable grouped backlog. The old "(Backlog)"
    # label set a false expectation (founder asked for a sorted, grouped,
    # browsable view that does not exist yet). See UX_TELEGRAM_AUDIT_DAY3.
    markup.add(telebot.types.KeyboardButton("🔍 השלמת יומן — הפריט הבא"))
    markup.add(telebot.types.KeyboardButton("🧹 ארכיון עסקאות (Legacy)"))
    markup.add(telebot.types.KeyboardButton("⬅️ חזרה לתפריט ראשי"))
    return markup


def get_rating_keyboard(t_id, field):
    keyboard = telebot.types.InlineKeyboardMarkup(row_width=5)
    btns = [telebot.types.InlineKeyboardButton(text=str(i), callback_data=f"v|{t_id}|{field}|{i}") for i in range(1, 11)]
    keyboard.add(*btns)
    keyboard.add(telebot.types.InlineKeyboardButton(text="⏭️ דילוג", callback_data=f"v|{t_id}|{field}|-1"))
    return keyboard


def get_setup_keyboard(t_id):
    keyboard = telebot.types.InlineKeyboardMarkup(row_width=2)
    for s in _SETUPS:
        keyboard.add(telebot.types.InlineKeyboardButton(text=s, callback_data=f"v|{t_id}|setup_type|{s}"))
    keyboard.add(telebot.types.InlineKeyboardButton(text="⏭️ דילוג", callback_data=f"v|{t_id}|setup_type|Skipped"))
    return keyboard
