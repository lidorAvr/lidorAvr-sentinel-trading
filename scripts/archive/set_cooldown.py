with open('/home/orangepi/sentinel_trading/main.py', 'r') as f:
    code = f.read()

if "IBKR_COOLDOWN_SECONDS" not in code:
    old_def = "def get_ibkr_trades():"
    
    new_def = """import time
LAST_IBKR_FETCH = 0
IBKR_COOLDOWN_SECONDS = 5 * 3600  # 5 hours

def get_ibkr_trades():
    global LAST_IBKR_FETCH
    if time.time() - LAST_IBKR_FETCH < IBKR_COOLDOWN_SECONDS:
        return []  # Skip IBKR fetch quietly if 5 hours haven't passed
    
    LAST_IBKR_FETCH = time.time()"""

    code = code.replace(old_def, new_def)
    
    with open('/home/orangepi/sentinel_trading/main.py', 'w') as f:
        f.write(code)
    print("✅ הוגדרה בהצלחה השהיה של 5 שעות בין משיכות מאינטראקטיב!")
else:
    print("⚠️ ההשהיה כבר מוגדרת בקוד.")
