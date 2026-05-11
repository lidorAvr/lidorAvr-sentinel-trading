import os
import re

with open('/home/orangepi/sentinel_trading/main.py', 'r') as f:
    code = f.read()

# מחיקת קוד הטלגרם הישן שניסינו לשתול קודם, למקרה שהוא שם
code = re.sub(r'try:\n\s+from bot_logic import send_telegram_msg.*?except:\n\s+pass', '', code, flags=re.DOTALL)

# קוד טלגרם ישיר ועצמאי שרץ מיד בעליית הקובץ
robust_tg = """
import requests
import os
def notify_boot_robust():
    try:
        tok = os.getenv("TELEGRAM_TOKEN")
        cid = os.getenv("TELEGRAM_CHAT_ID")
        if tok and cid:
            msg = "🔄 *מערכת Sentinel באוויר*\\nהבוט רץ וממתין ששרתי Supabase (אמזון) יחזרו לפעילות כדי לעדכן את הטריידים."
            requests.get(f"https://api.telegram.org/bot{tok}/sendMessage", params={"chat_id": cid, "text": msg}, timeout=10)
    except:
        pass
notify_boot_robust()
"""

if "notify_boot_robust" not in code:
    # נדביק את הפונקציה ממש בהתחלה, מיד אחרי import time
    code = code.replace("import time", "import time\n" + robust_tg)
    with open('/home/orangepi/sentinel_trading/main.py', 'w') as f:
        f.write(code)
    print("✅ קוד הטלגרם הושתל בהצלחה!")
else:
    print("⚠️ הקוד כבר קיים.")
