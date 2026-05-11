import os

path = '/home/orangepi/sentinel_trading/main.py'
with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 1. ניקוי יסודי של כל הזרקות העבר - מסירים שורות עם מילות מפתח בעייתיות
keywords = ['update_nav_locally', 'nav_node', 'nav_val', 'nav_el', 'ChangeInNAV', 'import json', '💾', '💰', 'report_root.find']
clean_lines = [line for line in lines if not any(k in line for k in keywords)]

# 2. פונקציית עדכון נקייה (עם 4 רווחים תקניים)
new_func = [
    "import json\n",
    "import os\n",
    "def update_nav_locally(val):\n",
    "    try:\n",
    "        cfg_path = '/app/sentinel_config.json'\n",
    "        data = {'total_deposited': 7500.0, 'risk_pct_input': 0.5}\n",
    "        if os.path.exists(cfg_path):\n",
    "            with open(cfg_path, 'r') as f: data = json.load(f)\n",
    "        data['nav'] = float(val)\n",
    "        with open(cfg_path, 'w') as f: json.dump(data, f)\n",
    "        print(f'NAV Updated: {val}')\n",
    "    except: pass\n",
    "\n"
]

# 3. הזרקה מחדש של הקריאה לפונקציה בתוך ה-Main Loop
final_lines = []
for line in clean_lines:
    final_lines.append(line)
    if "report_root = ET.fromstring" in line:
        # אנחנו מזהים את המרווח המקורי של השורה ומזריקים באותו קו
        indent = line[:line.find("report_root")]
        final_lines.append(f"{indent}try:\n")
        final_lines.append(f"{indent}    node = report_root.find('.//ChangeInNAV')\n")
        final_lines.append(f"{indent}    if node is not None: update_nav_locally(node.get('endingValue'))\n")
        final_lines.append(f"{indent}except: pass\n")

with open(path, 'w', encoding='utf-8') as f:
    f.writelines(new_func + final_lines)

print("✅ קובץ main.py שוחזר ונוקה מרווחים כפולים!")
