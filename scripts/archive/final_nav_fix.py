import os

file_path = '/home/orangepi/sentinel_trading/main.py'
with open(file_path, 'r') as f:
    code = f.read()

# תיקון הנתיב בכל מקום בקובץ
old_path = '/home/orangepi/sentinel_trading/sentinel_config.json'
new_path = '/app/sentinel_config.json'

if old_path in code:
    code = code.replace(old_path, new_path)
    with open(file_path, 'w') as f:
        f.write(code)
    print("✅ הנתיבים בתוך main.py תוקנו!")
else:
    print("⚠️ לא נמצאו נתיבים שגויים, בודק אם הבעיה בשמות המשתנים...")

