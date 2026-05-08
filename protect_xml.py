with open('/home/orangepi/sentinel_trading/main.py', 'r') as f:
    code = f.read()

# נחליף את בלוק ה-try הכללי בבלוק שיודע לתפוס שגיאות XML
old_except = """    except Exception as e:
        log(f"🚨 IBKR Error: {e}")"""

new_except = """    except ET.ParseError as e:
        log(f"⚠️ IBKR returned malformed data (likely 503 HTML). Server busy. ({e})")
        return []
    except Exception as e:
        log(f"🚨 IBKR Error: {e}")"""

if old_except in code:
    code = code.replace(old_except, new_except)
    with open('/home/orangepi/sentinel_trading/main.py', 'w') as f:
        f.write(code)
    print("✅ הגנת קריסת XML הותקנה בהצלחה!")
else:
    print("⚠️ לא מצאתי את בלוק ה-except. נסה לעדכן ידנית או שזה כבר קיים.")
