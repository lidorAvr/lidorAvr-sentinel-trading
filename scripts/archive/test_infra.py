import os
import requests
from dotenv import load_dotenv
try:
    from supabase import create_client
    HAS_SUPABASE = True
except ImportError:
    HAS_SUPABASE = False

load_dotenv('/home/orangepi/sentinel_trading/.env')

print("--- 📱 בודק חיבור לטלגרם ---")
tok = os.getenv("TELEGRAM_TOKEN")
cid = os.getenv("TELEGRAM_CHAT_ID")
if tok and cid:
    res = requests.get(f"https://api.telegram.org/bot{tok}/sendMessage", params={"chat_id": cid, "text": "🛠️ הודעת בדיקה ישירה מהשרת! טלגרם עובד."}, timeout=10)
    if res.status_code == 200:
        print("✅ טלגרם עובד מעולה! (היית אמור לקבל הודעה הרגע)")
    else:
        print(f"🚨 טלגרם החזיר שגיאה: {res.text}")
else:
    print("🚨 שגיאה: חסר טוקן או צ'אט ID בקובץ .env!")

print("\n--- 🗄️ בודק חיבור ל-Supabase ---")
if not HAS_SUPABASE:
    print("⚠️ ספריית supabase לא מותקנת בסביבה החיצונית, מדלג על בדיקה זו.")
else:
    supa_url = os.getenv("SUPABASE_URL")
    supa_key = os.getenv("SUPABASE_KEY")
    if supa_url and supa_key:
        try:
            supabase = create_client(supa_url, supa_key)
            res = supabase.table("trades").select("trade_id").limit(1).execute()
            print("✅ התחברות ל-Supabase הצליחה! השרת שלהם חזר לחיים.")
        except Exception as e:
            print(f"🚨 Supabase עדיין למטה (תקלת השרתים נמשכת). שגיאה: {e}")
    else:
        print("🚨 שגיאה: חסר URL או Key של Supabase בקובץ .env!")
