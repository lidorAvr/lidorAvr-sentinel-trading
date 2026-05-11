import os

def fix_file(path):
    if not os.path.exists(path):
        return
    with open(path, 'r') as f:
        code = f.read()
    
    # מחליף נתיב קשיח בנתיב פנימי של דוקר
    old_path = '/home/orangepi/sentinel_trading/sentinel_config.json'
    new_path = '/app/sentinel_config.json'
    
    if old_path in code:
        code = code.replace(old_path, new_path)
        with open(path, 'w') as f:
            f.write(code)
        print(f"✅ נתיב תוקן ב-{path}")
    else:
        print(f"ℹ️ לא נמצא נתיב שגוי ב-{path}")

fix_file('/home/orangepi/sentinel_trading/main.py')
fix_file('/home/orangepi/sentinel_trading/dashboard.py')
