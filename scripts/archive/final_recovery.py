import re
import textwrap

file_path = '/home/orangepi/sentinel_trading/main.py'
with open(file_path, 'r') as f:
    lines = f.readlines()

# 1. ניקוי אגרסיבי של כל הזרקות העבר
clean_lines = []
for line in lines:
    if any(x in line for x in ["update_nav_locally", "nav_node", "nav_el", "ChangeInNAV", "import json"]):
        continue
    clean_lines.append(line)

core_code = "".join(clean_lines).strip()

# 2. הגדרת הלוגיקה החדשה ללא רווחים מיותרים (Dedent)
header_logic = textwrap.dedent("""
    import json
    import os

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
            print(f"💾 NAV Updated: {val}")
        except:
            pass
""").strip()

# 3. הרכבת הקובץ מחדש
final_code = header_logic + "\n\n" + core_code

# 4. הזרקת הקריאה לפונקציה בתוך ה-Main Loop (בדיוק איפה שה-XML מעובד)
target = "report_root = ET.fromstring(res_data.text)"
replacement = textwrap.dedent(f"""
    {target}
        try:
            nav_node = report_root.find(".//ChangeInNAV")
            if nav_node is not None:
                v = nav_node.get('endingValue')
                if v: update_nav_locally(v)
        except: pass
""").strip()

if target in final_code:
    final_code = final_code.replace(target, replacement)

with open(file_path, 'w') as f:
    f.write(final_code)

print("✅ main.py נוקה, יושר ושוחזר בהצלחה!")
