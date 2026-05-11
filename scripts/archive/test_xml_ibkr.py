import os
import requests
from dotenv import load_dotenv

load_dotenv('/home/orangepi/sentinel_trading/.env')

IBKR_TOKEN = os.getenv("IBKR_TOKEN")
IBKR_QUERY_ID = os.getenv("IBKR_QUERY_ID")

print("⏳ שולח בקשה לאינטראקטיב (SendRequest)...")
send_url = "https://www.interactivebrokers.com/Universal/servlet/FlexStatementService.SendRequest"
res = requests.get(send_url, params={"t": IBKR_TOKEN, "q": IBKR_QUERY_ID, "v": "3"}, timeout=30)

print(f"\n--- קוד מצב HTTP: {res.status_code} ---")
print("\n--- הנה 25 השורות הראשונות של התשובה מאינטראקטיב ---")

lines = res.text.splitlines()
for i, line in enumerate(lines[:25]):
    print(f"{i+1}: {line}")

if len(lines) >= 18:
    print("\n⚠️ הנה שורה 18 הבעייתית שפייתון קורס עליה:")
    print(f"[{lines[17]}]")
else:
    print(f"\nהתשובה קצרה מ-18 שורות. סה\"כ: {len(lines)}")

