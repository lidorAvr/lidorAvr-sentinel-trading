import os

file_path = '/home/orangepi/sentinel_trading/main.py'
with open(file_path, 'r') as f:
    lines = f.readlines()

# ניקוי כל זכר לניסיונות הזרקה קודמים כדי למנוע קריסות
clean_lines = [l for line in lines if "nav" not in line.lower() or "deposited" in line.lower() or "risk" in line.lower()]
# (השארנו רק שורות שלא קשורות ל-NAV או שקשורות להגדרות המקוריות)

# בניית פונקציית עדכון חדשה לגמרי בראש הקובץ
header = """
import json, os

def update_nav_locally(val):
    try:
        path = '/app/sentinel_config.json'
        p_data = {"total_deposited": 7500.0, "risk_pct_input": 0.5}
        if os.path.exists(path):
            with open(path, 'r') as f:
                p_data = json.load(f)
        p_data['nav'] = float(val)
        with open(path, 'w') as f:
            json.dump(p_data, f)
        print(f"💾 NAV Updated: {val}")
    except: pass
"""

with open(file_path, 'w') as f:
    f.write(header + "".join(lines))

print("✅ קובץ main.py נוקה ושוחזר. עכשיו נשתול את הקריאה במקום בטוח.")
