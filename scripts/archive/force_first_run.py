import re

with open('/home/orangepi/sentinel_trading/main.py', 'r') as f:
    code = f.read()

# 1. הוספת דגל אתחול והודעת פתיחה בתחילת הלוגיקה
# נחפש את המקום שבו המשתנים הגלובליים מוגדרים
initial_setup = """
INITIAL_BOOT = True
LAST_SUCCESSFUL_SYNC_DATE = None
LAST_IBKR_ATTEMPT = 0

# שליחת הודעת עליית מערכת לטלגרם
try:
    from bot_logic import send_telegram_msg
    send_telegram_msg("🔄 *מערכת Sentinel עולה מחדש...*\\nמבצע סריקה ראשונית כפויה ומתחבר לאינטראקטיב.")
except:
    pass
"""

if "INITIAL_BOOT" not in code:
    # מזריקים את ההגדרות לפני פונקציית ה-get_ibkr_trades
    code = code.replace("def get_ibkr_trades():", initial_setup + "\ndef get_ibkr_trades():")

# 2. עדכון התנאי של השעה 06:00 שיתחשב בבוט הראשוני
old_condition = "if now.hour < 6:"
new_condition = "if not INITIAL_BOOT and now.hour < 6:"

if old_condition in code:
    code = code.replace(old_condition, new_condition)

# 3. ביטול הדגל אחרי הניסיון הראשון
if "INITIAL_BOOT = False" not in code:
    code = code.replace("trades = _get_ibkr_trades_core()", "INITIAL_BOOT = False\n    trades = _get_ibkr_trades_core()")

with open('/home/orangepi/sentinel_trading/main.py', 'w') as f:
    f.write(code)

print("✅ קוד 'התעוררות כפויה' והודעת פתיחה הוטמעו בהצלחה!")
