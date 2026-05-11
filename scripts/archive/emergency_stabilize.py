import re
import os

file_path = '/home/orangepi/sentinel_trading/main.py'
with open(file_path, 'r') as f:
    lines = f.readlines()

# 1. ניקוי אגרסיבי - מסירים כל שורה שמכילה "nav" או "update_nav_locally" 
# חוץ מהגדרות בסיסיות אם היו כאלו במקור.
clean_lines = []
for line in lines:
    low = line.lower()
    # אנחנו משאירים רק שורות שלא קשורות להזרקות ה-NAV הכושלות שלנו
    if "update_nav_locally" in line or "nav_node" in line or "nav_el" in line or "ChangeInNAV" in line:
        continue
    clean_lines.append(line)

new_code = "".join(clean_lines)

# 2. הזרקת הפונקציה והלוגיקה בצורה תקינה בראש הקובץ ובתוך הפונקציה
header_logic = """
import json

def update_nav_locally(val):
    try:
        path = '/app/sentinel_config.json'
        data = {"total_deposited": 7500.0, "risk_pct_input": 0.5}
        if os.path.exists(path):
            with open(path, 'r') as f:
                data = json.load(f)
        data['nav'] = float(val)
        with open(path, 'w') as f:
            json.dump(data, f)
        print(f"💾 NAV Auto-Updated: {val}")
    except:
        pass
"""

# מוסיפים את הפונקציה אחרי ה-imports
if "import os" in new_code:
    new_code = new_code.replace("import os", "import os" + header_logic, 1)

# 3. מציאת הנקודה שבה report_root נוצר והזרקת הקריאה שם
target_pattern = r"report_root = ET\.fromstring\(res_data\.text\)"
replacement = "report_root = ET.fromstring(res_data.text)\n    try:\n        nav_node = report_root.find('.//ChangeInNAV')\n        if nav_node is not None:\n            v = nav_node.get('endingValue')\n            if v: update_nav_locally(v)\n    except: pass"

new_code = re.sub(target_pattern, replacement, new_code)

with open(file_path, 'w') as f:
    f.write(new_code)

print("✅ קובץ main.py יוצב, נוקה ושודרג!")
