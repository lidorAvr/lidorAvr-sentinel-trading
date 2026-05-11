import os

file_path = '/home/orangepi/sentinel_trading/main.py'
with open(file_path, 'r') as f:
    lines = f.readlines()

# 1. ניקוי רעלים: מסירים כל שורה שקשורה ל-NAV או להזרקות שלנו מהיום
# אנחנו משאירים רק את הלוגיקה המקורית של הבוט
clean_lines = []
for line in lines:
    skip = False
    # רשימת מילים שאנחנו רוצים לנקות כדי להחזיר את הקובץ למצב "בתולי"
    trigger_words = ["update_nav_locally", "nav_node", "nav_val", "nav_el", "ChangeInNAV", "import json"]
    if any(word in line for word in trigger_words):
        continue
    clean_lines.append(line)

# 2. בניית הבלוק החדש - מיושר ב-100% (4 רווחים)
new_header = [
    "import json\n",
    "import os\n",
    "def update_nav_locally(val):\n",
    "    try:\n",
    "        path = '/app/sentinel_config.json'\n",
    "        data = {'total_deposited': 7500.0, 'risk_pct_input': 0.5}\n",
    "        if os.path.exists(path):\n",
    "            with open(path, 'r') as f:\n",
    "                data = json.load(f)\n",
    "        data['nav'] = float(val)\n",
    "        with open(path, 'w') as f:\n",
    "            json.dump(data, f)\n",
    "        print(f'💾 NAV Updated: {val}')\n",
    "    except Exception as e:\n",
    "        print(f'🚨 NAV Save Error: {e}')\n",
    "\n"
]

# 3. מציאת המקום המדויק להזרקת הקריאה בתוך הריצה של אינטראקטיב
final_lines = new_header + clean_lines
new_content = "".join(final_lines)

# הזרקת הקריאה לפונקציה מיד אחרי קבלת הדו"ח
target = "report_root = ET.fromstring(res_data.text)"
if target in new_content:
    replacement = target + "\n    try:\n        node = report_root.find('.//ChangeInNAV')\n        if node is not None:\n            v = node.get('endingValue')\n            if v: update_nav_locally(v)\n    except: pass"
    new_content = new_content.replace(target, replacement)

with open(file_path, 'w') as f:
    f.write(new_content)

print("✅ קובץ main.py שוחזר, נוקה ויושר באופן מושלם!")
