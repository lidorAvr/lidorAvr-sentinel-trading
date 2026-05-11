with open('/home/orangepi/sentinel_trading/main.py', 'r') as f:
    code = f.read()

# מתקנים את הצהרת הגלובל בתוך הפונקציה
old_global = "global LAST_SUCCESSFUL_SYNC_DATE, LAST_IBKR_ATTEMPT"
new_global = "global LAST_SUCCESSFUL_SYNC_DATE, LAST_IBKR_ATTEMPT, INITIAL_BOOT"

if old_global in code:
    code = code.replace(old_global, new_global)
    with open('/home/orangepi/sentinel_trading/main.py', 'w') as f:
        f.write(code)
    print("✅ משתנה INITIAL_BOOT הוגדר כגלובלי בהצלחה!")
else:
    print("⚠️ לא מצאתי את שורת ה-global. אולי היא כבר תוקנה?")

