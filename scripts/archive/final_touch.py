file_path = '/home/orangepi/sentinel_trading/main.py'
with open(file_path, 'r') as f:
    code = f.read()

# הזרקה מיד אחרי שנוצר ה-report_root
target = "report_root = ET.fromstring(res_data.text)"
injection = """
    report_root = ET.fromstring(res_data.text)
    try:
        nav_node = report_root.find(".//ChangeInNAV")
        if nav_node is not None:
            v = nav_node.get('endingValue')
            if v: update_nav_locally(v)
    except: pass
"""

if target in code and "nav_node" not in code:
    code = code.replace(target, injection)
    with open(file_path, 'w') as f:
        f.write(code)
    print("✅ לוגיקת ה-NAV הוזרקה בהצלחה לתוך הליבה!")
else:
    print("⚠️ לא נמצא מקום להזרקה או שכבר קיים.")
