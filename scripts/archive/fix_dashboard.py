import re

file_path = '/home/orangepi/sentinel_trading/dashboard.py'
with open(file_path, 'r') as f:
    code = f.read()

# מחפש את הגדרת הפונקציה עם 2 ארגומנטים ומוסיף את השלישי
# מתקן: def save_settings(a, b): -> def save_settings(a, b, saved_nav=None):
code = re.sub(r'def save_settings\(([^,]+),\s*([^)]+)\):', r'def save_settings(\1, \2, saved_nav=None):', code)

with open(file_path, 'w') as f:
    f.write(code)

print("✅ פונקציית save_settings תוקנה בהצלחה!")
