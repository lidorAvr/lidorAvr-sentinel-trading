"""
Shared Telegram bot and Supabase instances for Sentinel Trading.

Import from here to avoid re-creating instances across modules.
"""
import os
import telebot
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()
TOKEN    = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_ID = os.getenv("TELEGRAM_ADMIN_ID")

bot      = telebot.TeleBot(TOKEN)
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
user_state: dict = {}
RTL = "‏"
