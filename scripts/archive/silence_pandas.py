with open('/home/orangepi/sentinel_trading/main.py', 'r') as f:
    code = f.read()

if "pd.options.mode.chained_assignment" not in code:
    code = code.replace("import pandas as pd", "import pandas as pd\npd.options.mode.chained_assignment = None")
    with open('/home/orangepi/sentinel_trading/main.py', 'w') as f:
        f.write(code)
    print("✅ אזהרות פנדס הושתקו בהצלחה!")
else:
    print("ההשתקה כבר קיימת.")
