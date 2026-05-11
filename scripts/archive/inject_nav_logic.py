import os

file_path = '/home/orangepi/sentinel_trading/main.py'
with open(file_path, 'r') as f:
    code = f.read()

# 1. נוודא שהספריות הנדרשות מיובאות
if "import json" not in code:
    code = "import json\n" + code

# 2. הזרקת פונקציית העדכון (בצורה שתעבוד בתוך דוקר)
nav_func = """
def update_nav_locally(nav_value):
    path = '/app/sentinel_config.json'
    try:
        data = {}
        if os.path.exists(path):
            with open(path, 'r') as f:
                data = json.load(f)
        data['nav'] = float(nav_value)
        with open(path, 'w') as f:
            json.dump(data, f)
        log(f"💾 שווי תיק מעודכן נשמר: ${nav_value}")
    except Exception as e:
        log(f"🚨 שגיאה בשמירת NAV: {e}")
"""

if "def update_nav_locally" not in code:
    code = nav_func + "\n" + code

# 3. הזרקת הלוגיקה שסורקת את ה-XML ומחפשת את ה-NAV
# אנחנו נשתול את זה מיד אחרי שהבוט מסיים לעבור על הטריידים
nav_parsing_logic = """
    # חילוץ NAV מהדו"ח
    nav_elem = report_root.find(".//ChangeInNAV")
    if nav_elem is not None:
        nav_val = nav_elem.get('endingValue')
        if nav_val:
            update_nav_locally(nav_val)
"""

if "ChangeInNAV" not in code:
    # נחפש את המקום שבו הוא מסיים לטפל בטריידים (trades = report_root.findall)
    if "trades = report_root.findall" in code:
        code = code.replace("trades = report_root.findall", nav_parsing_logic + "\n    trades = report_root.findall")
        with open(file_path, 'w') as f:
            f.write(code)
        print("✅ לוגיקת NAV הוזרקה בהצלחה לקוד!")
    else:
        print("🚨 לא מצאתי את המיקום המדויק להזרקה. בודק שיטה חלופית...")
        # שיטה חלופית - הזרקה בסוף הפונקציה המרכזית
        code = code.replace("return trades", nav_parsing_logic + "\n    return trades")
        with open(file_path, 'w') as f:
            f.write(code)
        print("✅ לוגיקת NAV הוזרקה בשיטה חלופית!")
