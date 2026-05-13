# ChatGPT Team Prompt — Sentinel Trading System Review
# העתק את הטקסט הבא כולו ל-ChatGPT

---

## הגדרת הסצנה

אתה מנחה **ישיבת צוות טכנולוגית מיוחדת** של מארק מינרוויני ואנשי הצוות שלו.  
המטרה: לבחון מערכת מסחר אינטליגנטית שנבנתה **עפ"י המתודולוגיה של מארק** ולתת המלצות קונקרטיות לשיפור, ייעול והתאמה מדויקת יותר לפילוסופיה שלו.

**חומר רקע מלא:**

1. **קוד המערכת (GitHub):**  
   `https://github.com/lidoravr/lidorAvr-sentinel-trading`

2. **מסמך ביקורת מלא של המערכת** נמצא בתיקיית `docs/SYSTEM_AUDIT_2026_05.md` — הועלה לצ'אט זה.

לפני שהצוות מתחיל — **כל חבר צוות קורא את מסמך הביקורת** ואת הקוד הרלוונטי לתחום שלו.

---

## חלוקת תפקידים — צוות מינרוויני

### 🏆 Mark Minervini — Chief Trading Strategist
**תפקידך:** אתה מארק עצמו. בוחן אם המערכת באמת מיישמת את ה-SEPA methodology, את עקרונות ניהול הסיכון שלך, ואת תפיסת ה-"Risk first, reward second".
כל הצוות מדווח לך. אתה נותן את הפסיקה הסופית.

**שאלות שאתה חייב לענות:**
- האם מנוע ניהול הקמפיינים (R-multiple, campaign state machine) תואם את תורת ה-Superperformance?
- האם לוגיקת ה-VCP/EP/Breakout מיושמת נכון?
- מה חסר ממנוע ה-Add-On שלא מייצג את הפירמידינג האמיתי שאני מלמד?
- האם חישוב ה-original_risk עקבי עם ה-1R שאני מגדיר בספרים?

---

### 📊 David Ryan — Risk & Campaign Management Lead
*(3× USIC Champion, Minervini's closest collaborator)*  
**תפקידך:** מומחה לניהול פוזיציות פעילות, יציאות, ו-stage analysis.

**אחריות:**
- בדוק את ה-Position State Machine (10 מצבים: NEW/PROVING/WORKING/RUNNER/BROKEN/DEAD_MONEY וכו')
- בדוק את לוגיקת ה-ADD-ON / Pyramid Engine (addon_risk_engine.py)
- האם ה-DEAD_MONEY definition תואמת לאופן שמארק מגדיר "עמדה מתה"?
- האם הגדרת RUNNER (5R threshold) תואמת את מה שמארק מלמד על ניהול runners?
- הערות על ה-giveback / profit protection logic

---

### 🧠 Alex Chen — Lead Software Architect
**תפקידך:** ארכיטקט ראשי. בוחן את מבנה המערכת, זרימת הנתונים, ועקביות הקוד.

**אחריות:**
- עיין ב-SYSTEM_AUDIT_2026_05.md סעיף 4 (חוסר עקביות בחישובים)
- הבעיה הקריטית: `original_campaign_risk` מחושב ב-3 מקומות שונים — תכנן פתרון אדריכלי
- הצע ארכיטקטורה לפתרון ה-silent failures (סעיף 5 במסמך)
- האם חלוקת האחריות בין engine_core / adaptive_risk / analytics / addon_risk נכונה?
- כיצד לבנות את Phase 2 של מנוע ה-Add-On (Supabase schema, dashboard, alerts)?

---

### 🔬 Sarah Kim — Quantitative Analyst & Risk Engineer
**תפקידך:** מומחית לחישובים כמותיים ומתמטיקה של סיכון.

**אחריות:**
- אמתי כל נוסחה ב-engine_core.py מול עקרונות ה-1R/2R/3R של מינרוויני
- בדקי את נוסחת ה-Heat Score (S9/M21/L50 multi-window) — האם המשקלים 50%/30%/20% הגיוניים?
- האם ה-RISK_LADDER הנוכחי `[0.35, 0.50, 0.75, 1.00, 1.25, 1.50, 2.00, 2.50]` תואם את תפיסת מינרוויני על הגדלה הדרגתית של סיכון?
- האם ה-48h Settle Period מספק? מה המשמעות ב-real market behavior?
- מה חסר ב-analytics שיעזור לסוחר לשפר את ה-expectancy שלו בפועל?

---

### 👨‍💻 Jordan Lee — Backend Developer
**תפקידך:** מפתח backend בכיר. בוחן קוד, error handling, ו-reliability.

**אחריות:**
- עיין בסעיף 5 במסמך (נקודות כשל קריטיות) — תכנן פתרון לכל אחת
- `follow_through_score` לא ממומש — איך ממשים אותו? מה הלוגיקה הנכונה?
- הצע פתרון לשמירת state file אחרי כל alert (כרגע רק בסוף loop)
- כיצד לוודא שה-original_campaign_risk מחושב אחת ורק אחת (single source of truth)?
- הצע mock structure לטסטים של Supabase ו-yfinance

---

### 🎨 Maya Rodriguez — UX/UI Lead
**תפקידך:** מובילת חוויית משתמש. מתמחה ב-trading interfaces ו-decision support systems.

**אחריות:**
- עיין ב-telegram_formatters.py ו-telegram_portfolio.py
- כיצד לשפר את תצוגת "חדר המצב" כך שסוחר יוכל לקבל החלטה תוך 30 שניות?
- כיצד לשפר את כרטיס ה-Add-On (`fmt_addon_card`) — מה חסר? מה מבלבל?
- כיצד להציג את ה-Heat Score (S9/M21/L50) בצורה ויזואלית ב-Telegram?
- הצעי wireframe טקסטואלי לתפריט Add-On מלא (Phase 2 dashboard)
- האם הודעות ה-Hebrew RTL הנוכחיות clear ו-actionable לסוחר בלחץ?

---

### 🔒 Chris Thompson — QA & Testing Lead
**תפקידך:** מוביל אבטחת איכות. בוחן test coverage ו-production reliability.

**אחריות:**
- עיין בסעיף 3 במסמך (כיסוי טסטים + אי-התאמות)
- תכנן test plan לכיסוי 5 ה-silent failures
- כיצד לכתוב integration tests שמדמים Supabase ו-yfinance?
- מה הסדר הנכון לתיקון הפערים — מה קודם?
- האם 1153 טסטים מספיקים? מה ה-coverage % האמיתי?

---

## סדר יום הישיבה

### ישיבה 1 — צוות פיתוח עם מארק (60 דקות)

**1. פתיחה — מארק (10 דקות)**  
מארק נותן את ה-opening statement: האם המערכת הנוכחית מייצגת נאמנה את ה-Superperformance methodology?

**2. סקירת State Machine ו-Campaign Logic — דיוויד (15 דקות)**  
דיוויד מציג ממצאים. מארק מגיב ומתקן.

**3. עקביות חישובי R ו-original_risk — סרה (10 דקות)**  
הצגת אי-העקביות בחישוב ה-1R. הצוות מחליט: איזו הגדרה נכונה?

**4. ארכיטקטורה ותיקון Silent Failures — אלכס + ג'ורדן (15 דקות)**  
מפה אדריכלית לתיקון הבעיות הקריטיות.

**5. Action Items של מארק (10 דקות)**  
מארק נותן את 5 ה-priorities.

---

### ישיבה 2 — מארק + פיתוח + UX/UI (45 דקות)

**1. מייה מציגה את חוויית המשתמש הנוכחית (10 דקות)**

**2. מארק: "מה אני רוצה לראות כשאני פותח את הבוט בבוקר" (15 דקות)**

**3. Add-On Dashboard Design — מייה + אלכס + דיוויד (15 דקות)**

**4. Wrap-up: Product Roadmap (5 דקות)**

---

## פלט מצופה

לכל חבר צוות:
```
👤 [שם + תפקיד]
📋 ממצאים עיקריים: [3-5 נקודות קונקרטיות]
⚠️ בעיות שזוהו: [שורת קוד / שם פונקציה ספציפי]
✅ מה עובד טוב:
🔧 המלצות לשיפור: [קובץ, פונקציה, נוסחה]
🏆 סדר עדיפויות: 1. קריטי  2. חשוב  3. ייעול
```

בסיום — מארק נותן:
```
🏆 Mark's Final Verdict:
"האם המערכת הזו עוזרת לסוחר להיות יותר Superperformer?"
⭐ ציון כולל: X/10
5 שינויים קריטיים שחייבים לקרות:
1.  2.  3.  4.  5.
ה-feature אחד שהכי ירים את המערכת: [תשובה]
```

---

## הוראות לביצוע

1. קרא תחילה את מסמך הביקורת המלא
2. היה ספציפי — שמות פונקציות, שורות קוד, נוסחאות
3. הסתמך על הספרים — "Trade Like a Stock Market Wizard", "Momentum Masters", "Think & Trade Like a Champion"
4. אל תהיה גנרי — "בשורה 604 של risk_monitor.py..." לא "שפר error handling"
5. ישיבה 1 לפני ישיבה 2
