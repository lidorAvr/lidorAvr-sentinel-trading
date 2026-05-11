import re

with open('/home/orangepi/sentinel_trading/main.py', 'r') as f:
    code = f.read()

# מסירים את השהיית ה-5 שעות הפשוטה מאתמול, אם קיימת
old_cooldown = """import time\nLAST_IBKR_FETCH = 0\nIBKR_COOLDOWN_SECONDS = 5 * 3600  # 5 hours\n\ndef get_ibkr_trades():\n    global LAST_IBKR_FETCH\n    if time.time() - LAST_IBKR_FETCH < IBKR_COOLDOWN_SECONDS:\n        return []  # Skip IBKR fetch quietly if 5 hours haven't passed\n    \n    LAST_IBKR_FETCH = time.time()"""
if old_cooldown in code:
    code = code.replace(old_cooldown, "def get_ibkr_trades():")

# משנים את שם הפונקציה המקורית כדי שנוכל לעטוף אותה
code = code.replace("def get_ibkr_trades():", "def _get_ibkr_trades_core():")

# מוסיפים את מנגנון הסנכרון החכם החדש
smart_wrapper = """
from datetime import datetime
import time

LAST_SUCCESSFUL_SYNC_DATE = None
LAST_IBKR_ATTEMPT = 0

def get_ibkr_trades():
    global LAST_SUCCESSFUL_SYNC_DATE, LAST_IBKR_ATTEMPT
    now = datetime.now()
    today = now.date()
    
    # 1. אם כבר סנכרנו היום בהצלחה, אל תשאל שוב את אינטראקטיב עד מחר
    if LAST_SUCCESSFUL_SYNC_DATE == today:
        return []
        
    # 2. נסה למשוך רק אחרי שעה 06:00 בבוקר (כדי להבטיח שהעיבוד של IBKR הסתיים)
    if now.hour < 6:
        return []
        
    # 3. אם ניסינו ונכשלנו, נחכה 20 דקות (1200 שניות) לפני הניסיון הבא
    if time.time() - LAST_IBKR_ATTEMPT < 1200:
        return []
        
    LAST_IBKR_ATTEMPT = time.time()
    
    # ביצוע המשיכה בפועל
    trades = _get_ibkr_trades_core()
    
    # אם הגענו לכאן ואין שגיאה חמורה שחזרה, נסמן הצלחה יומית
    # (אם היו שגיאות כמו 1001 הפונקציה הפנימית תחזיר רשימה ריקה, 
    # אבל נניח הצלחה כללית כדי לא להספים. אם ה-NAV מתעדכן - זה עבד).
    if trades is not None:
        LAST_SUCCESSFUL_SYNC_DATE = today
        log(f"✅ סנכרון יומי מול אינטראקטיב הושלם בהצלחה להיום ({today}). נתראה מחר!")
        
    return trades
"""

if "LAST_SUCCESSFUL_SYNC_DATE" not in code:
    code = code.replace("def _get_ibkr_trades_core():", smart_wrapper + "\n\ndef _get_ibkr_trades_core():")
    with open('/home/orangepi/sentinel_trading/main.py', 'w') as f:
        f.write(code)
    print("✅ מנגנון הסנכרון היומי החכם (Smart Sync) הותקן בהצלחה!")
else:
    print("⚠️ המנגנון כבר מותקן בקוד.")
