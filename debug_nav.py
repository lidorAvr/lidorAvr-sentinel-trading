import os

file_path = '/home/orangepi/sentinel_trading/main.py'
with open(file_path, 'r') as f:
    code = f.read()

# מזריקים הדפסה של ה-NAV מיד כשהוא נשלף
debug_line = '            log(f"💰 שווי תיק (NAV) שנמצא בדו\"ח: ${nav_value}")'
if 'nav_value = float(nav_elem.get("endingValue", 0))' in code and debug_line not in code:
    code = code.replace(
        'nav_value = float(nav_elem.get("endingValue", 0))',
        'nav_value = float(nav_elem.get("endingValue", 0))\n' + debug_line
    )
    with open(file_path, 'w') as f:
        f.write(code)
    print("✅ הוספתי לוג מעקב ל-NAV!")
else:
    print("⚠️ לא הצלחתי למצוא את המקום הנכון להזריק את הלוג או שהוא כבר שם.")
