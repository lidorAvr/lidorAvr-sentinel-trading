import os
import requests
import time
import xml.etree.ElementTree as ET
from dotenv import load_dotenv

load_dotenv('/home/orangepi/sentinel_trading/.env')

IBKR_TOKEN = os.getenv("IBKR_TOKEN")
IBKR_QUERY_ID = os.getenv("IBKR_QUERY_ID")

print("⏳ שולח בקשת לייב לאינטראקטיב...")
send_url = "https://www.interactivebrokers.com/Universal/servlet/FlexStatementService.SendRequest"
res = requests.get(send_url, params={"t": IBKR_TOKEN, "q": IBKR_QUERY_ID, "v": "3"}, timeout=30)
root = ET.fromstring(res.text)

status_tag = root.find(".//Status")
if status_tag is not None and status_tag.text == "Fail":
    print("🚨 שגיאה (כנראה 1001 Server Busy):")
    print(res.text)
    exit()

ref_code_elem = root.find(".//ReferenceCode")
if ref_code_elem is None:
    print(f"⚠️ לא מצאתי קוד ייחוס בתשובה. התשובה המלאה:\n{res.text}")
    exit()
    
ref_code = ref_code_elem.text
print(f"✅ קוד ייחוס התקבל: {ref_code}")

for attempt in range(1, 6):
    print(f"🔄 ניסיון משיכה {attempt}/5...")
    time.sleep(15)
    url_get = "https://www.interactivebrokers.com/Universal/servlet/FlexStatementService.GetStatement"
    res_data = requests.get(url_get, params={"q": ref_code, "t": IBKR_TOKEN, "v": "3"}, timeout=30)
    
    if "<Flex" in res_data.text or "<Trade" in res_data.text:
        print("\n✅ הדו\"ח נמשך בהצלחה!")
        # מציג קצת מהדו"ח כדי שנדע שזה אמיתי
        print(res_data.text[:300] + "...\n")
        exit()
    elif "Statement generation in progress" in res_data.text:
        continue
    else:
        print(f"⚠️ תשובה לא צפויה: {res_data.text}")
        exit()

print("❌ תם הזמן (Timeout). אינטראקטיב לא סיימו לייצר את הדו\"ח.")
