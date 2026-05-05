import os
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
from supabase import create_client

# טעינת משתני הסביבה
load_dotenv('/home/orangepi/sentinel_trading/.env')
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("🚨 שגיאה: לא נמצאו מזהי Supabase בקובץ ה-.env")
    exit(1)

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
table_name = "trades"

print(f"⏳ מתחיל גיבוי של טבלת '{table_name}' מ-Supabase...")

all_data = []
offset = 0
limit = 1000

# לולאה שמושכת את כל הנתונים (גם אם יש מעל 1000 עסקאות)
while True:
    print(f"🔄 מושך שורות {offset} עד {offset + limit}...")
    res = supabase.table(table_name).select("*").range(offset, offset + limit - 1).execute()
    
    if not res.data:
        break
        
    all_data.extend(res.data)
    
    # אם קיבלנו פחות מהלימיט, סימן שהגענו לסוף הטבלה
    if len(res.data) < limit:
        break
        
    offset += limit

if all_data:
    df = pd.DataFrame(all_data)
    
    # סידור העמודות ככה שיהיה נוח לקרוא
    if 'trade_date' in df.columns:
        df = df.sort_values(by='trade_date', ascending=False)
        
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = "/app/_stable_backups"
    os.makedirs(backup_dir, exist_ok=True)
    
    csv_path = os.path.join(backup_dir, f"supabase_backup_{timestamp}.csv")
    json_path = os.path.join(backup_dir, f"supabase_backup_{timestamp}.json")
    
    # שמירה ל-CSV (עם קידוד מיוחד כדי שעברית תעבוד באקסל)
    df.to_csv(csv_path, index=False, encoding='utf-8-sig')
    # שמירה ל-JSON
    df.to_json(json_path, orient='records', force_ascii=False, indent=4)
    
    print("\n✅ הגיבוי הושלם בהצלחה!")
    print(f"📊 נמשכו סך הכל {len(df)} עסקאות.")
    print(f"📁 קובץ CSV (לאקסל): {csv_path}")
    print(f"📁 קובץ JSON (למערכת): {json_path}")
else:
    print("⚠️ הטבלה ריקה או שלא התקבלו נתונים.")
