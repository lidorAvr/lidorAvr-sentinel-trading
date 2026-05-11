import json
import os

file_path = '/home/orangepi/sentinel_trading/main.py'
with open(file_path, 'r') as f:
    code = f.read()

# הגדרת פונקציית שמירה חדשה וחסינה
new_nav_func = """
def update_nav_locally(nav_value):
    config_path = '/app/sentinel_config.json'
    try:
        data = {}
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                data = json.load(f)
        
        data['nav'] = float(nav_value)
        with open(config_path, 'w') as f:
            json.dump(data, f)
        log(f"💾 NAV נשמר בהצלחה: ${nav_value}")
    except Exception as e:
        log(f"🚨 שגיאה בשמירת NAV: {e}")
"""

# הזרקת הפונקציה לקוד אם היא לא קיימת
if "update_nav_locally" not in code:
    code = "import json\n" + new_nav_func + "\n" + code

# וידוא שקוראים לפונקציה הזו בזמן הסנכרון
# אנחנו נחפש את המקום שבו הוא מוצא את ה-NAV ב-XML ונדאג שהוא יקרא לפונקציה שלנו
if 'nav_value =' in code:
     # הזרקת קריאה לעדכון מיד אחרי מציאת הערך
     code = code.replace('nav_value = float', 'update_nav_locally(nav_value)\n            nav_value = float', 1)

with open(file_path, 'w') as f:
    f.write(code)
print("✅ מערכת עדכון ה-NAV שודרגה!")
