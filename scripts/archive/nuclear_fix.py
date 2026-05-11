import re

file_path = '/home/orangepi/sentinel_trading/main.py'
with open(file_path, 'r') as f:
    lines = f.readlines()

clean_lines = []
skip = False

# 1. ניקוי יסודי של כל הזרקות העבר שגרמו לקריסות
for line in lines:
    if "update_nav_locally(nav_val)" in line or "report_root.find('.//ChangeInNAV')" in line or "def update_nav_locally" in line:
        continue
    if "import json" in line and lines.index(line) > 10: # מסיר אימפורטים כפולים באמצע הקובץ
        continue
    clean_lines.append(line)

new_code = "".join(clean_lines)

# 2. הזרקת הפונקציה בצורה גלובלית בראש הקובץ
nav_func = """
def update_nav_locally(nav_value):
    try:
        import json, os
        path = '/app/sentinel_config.json'
        data = {}
        if os.path.exists(path):
            with open(path, 'r') as f:
                data = json.load(f)
        data['nav'] = float(nav_value)
        with open(path, 'w') as f:
            json.dump(data, f)
        print(f"💾 NAV updated: ${nav_value}")
    except Exception as e:
        print(f"🚨 NAV Update Error: {e}")
"""

# הזרקה אחרי האימפורטים
new_code = "import json, os\n" + nav_func + "\n" + new_code

# 3. הזרקה לתוך פונקציית הליבה שבה report_root קיים בוודאות
# אנחנו נחפש את המקום שבו הוא מוציא את הטריידים מה-XML
if 'report_root.findall' in new_code:
    pattern = r"( +)(trades = report_root\.findall\(.+?\))"
    replacement = r"\1nav_el = report_root.find('.//ChangeInNAV')\n\1if nav_el is not None:\n\1    val = nav_el.get('endingValue')\n\1    if val: update_nav_locally(val)\n\1\2"
    new_code = re.sub(pattern, replacement, new_code)

with open(file_path, 'w') as f:
    f.write(new_code)
print("✅ הקוד נוקה משגיאות ולוגיקת ה-NAV הושתלה בבטחה!")
