import re

with open('/home/orangepi/sentinel_trading/main.py', 'r') as f:
    code = f.read()

# 1. החלפת הודעת הטלגרם השקטה בבקשה ישירה ובלתי שבירה
old_tg = """try:
    from bot_logic import send_telegram_msg
    send_telegram_msg("🔄 *מערכת Sentinel עולה מחדש...*\\nמבצע סריקה ראשונית כפויה ומתחבר לאינטראקטיב.")
except:
    pass"""

new_tg = """import requests
import os
def notify_boot():
    try:
        tok = os.getenv("TELEGRAM_TOKEN")
        cid = os.getenv("TELEGRAM_CHAT_ID")
        msg = "🔄 *מערכת Sentinel עולה מחדש...*\\nשלב 1: מתחיל משיכה מאינטראקטיב וחיבור ל-Supabase."
        if tok and cid:
            requests.get(f"https://api.telegram.org/bot{tok}/sendMessage", params={"chat_id": cid, "text": msg}, timeout=10)
            print("✅ הודעת התעוררות נשלחה לטלגרם בהצלחה!")
    except Exception as e:
        print(f"🚨 שגיאה בשליחת הודעת התעוררות לטלגרם: {e}")
notify_boot()"""

if "from bot_logic import send_telegram_msg" in code:
    code = code.replace(old_tg, new_tg)

# 2. הוספת לוגים מפורטים לשלבי המשיכה
old_sync = "trades = _get_ibkr_trades_core()"
new_sync = """log("⏳ [שלב 1] מתחיל משיכת נתונים מאינטראקטיב (IBKR)...")
    trades = _get_ibkr_trades_core()
    if trades is not None:
        log(f"✅ [שלב 2] הדו\"ח נמשך בהצלחה! נמצאו {len(trades)} טריידים גולמיים בדו\"ח של אינטראקטיב.")
        log("⏳ [שלב 3] מנתח נתונים ומנסה לעדכן את מסד הנתונים (Supabase)...")
    else:
        log("⚠️ [שלב 2] משיכה מאינטראקטיב נכשלה או שהדו\"ח חזר ריק.")"""

if "שלב 1" not in code:
    code = code.replace(old_sync, new_sync)

with open('/home/orangepi/sentinel_trading/main.py', 'w') as f:
    f.write(code)

print("✅ שדרוג הלוגים בוצע בהצלחה!")
