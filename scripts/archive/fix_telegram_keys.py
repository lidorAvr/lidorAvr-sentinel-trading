with open('/home/orangepi/sentinel_trading/main.py', 'r') as f:
    code = f.read()

# מתקנים את השמות למשתנים האמיתיים שיש לך בקובץ .env
code = code.replace('os.getenv("TELEGRAM_TOKEN")', 'os.getenv("TELEGRAM_BOT_TOKEN")')
code = code.replace('os.getenv("TELEGRAM_CHAT_ID")', 'os.getenv("TELEGRAM_ADMIN_ID")')

with open('/home/orangepi/sentinel_trading/main.py', 'w') as f:
    f.write(code)
print("✅ שמות משתני הטלגרם תוקנו בקוד!")
