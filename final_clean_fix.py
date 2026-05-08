import re

file_path = '/home/orangepi/sentinel_trading/main.py'
with open(file_path, 'r') as f:
    code = f.read()

# 1. הסרת הקוד שגרם לקריסה (ניקוי הזרקות קודמות)
code = re.sub(r'\s+# חילוץ NAV מהדו"ח.*?update_nav_locally\(nav_val\)', '', code, flags=re.DOTALL)
code = code.replace("return trades\n\n    # חילוץ NAV מהדו\"ח", "return trades")

# 2. הגדרת פונקציית עדכון NAV נקייה בתחילת הקובץ
nav_func = """
def update_nav_locally(nav_value):
    path = '/app/sentinel_config.json'
    try:
        import json, os
        data = {}
        if os.path.exists(path):
            with open(path, 'r') as f:
                data = json.load(f)
        data['nav'] = float(nav_value)
        with open(path, 'w') as f:
            json.dump(data, f)
        log(f"💾 NAV מעודכן נשמר בקובץ: ${nav_value}")
    except Exception as e:
        log(f"🚨 שגיאה בשמירת NAV: {e}")
"""

if "def update_nav_locally" not in code:
    code = "import json\n" + nav_func + "\n" + code

# 3. הזרקה חכמה לתוך הליבה שבה report_root קיים בוודאות
# אנחנו נחפש את השורה שבה הבוט מוצא את הטריידים ב-XML
target = "trades = report_root.findall('.//Trade')"
replacement = """
    # חילוץ NAV בתוך הסקופ הנכון
    nav_el = report_root.find('.//ChangeInNAV')
    if nav_el is not None:
        val = nav_el.get('endingValue')
        if val:
            update_nav_locally(val)
    
    trades = report_root.findall('.//Trade')"""

if target in code:
    code = code.replace(target, replacement)
    with open(file_path, 'w') as f:
        f.write(code)
    print("✅ הקוד תוקן וה-NAV הוזרק למקום הנכון!")
else:
    print("🚨 לא מצאתי את שורת היעד. בודק גרסה חלופית...")
    target2 = "trades = report_root.findall(\".//Trade\")"
    if target2 in code:
        code = code.replace(target2, replacement)
        with open(file_path, 'w') as f:
            f.write(code)
        print("✅ הקוד תוקן (גרסה 2)!")
