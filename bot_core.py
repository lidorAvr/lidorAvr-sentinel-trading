"""
Shared Telegram bot and Supabase instances for Sentinel Trading.

Import from here to avoid re-creating instances across modules.
"""
import os
import telebot
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise SystemExit("TELEGRAM_BOT_TOKEN is not set")

_admin_raw = os.getenv("TELEGRAM_ADMIN_ID")
try:
    ADMIN_ID = int(_admin_raw)
except (TypeError, ValueError):
    raise SystemExit(f"TELEGRAM_ADMIN_ID must be an integer, got {_admin_raw!r}")
if ADMIN_ID <= 0:
    raise SystemExit(f"TELEGRAM_ADMIN_ID must be a positive integer, got {ADMIN_ID}")

_supabase_url = os.getenv("SUPABASE_URL")
_supabase_key = os.getenv("SUPABASE_KEY")
if not _supabase_url or not _supabase_key:
    raise SystemExit("SUPABASE_URL and SUPABASE_KEY must be set")

bot      = telebot.TeleBot(TOKEN)
supabase = create_client(_supabase_url, _supabase_key)
user_state: dict = {}
RTL = "‏"
