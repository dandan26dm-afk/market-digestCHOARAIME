# Market Digest 📊

תמונת סיכום שוק שנשלחת לדיסקורד כל יום מסחר, שעה אחרי הפתיחה בוול סטריט (10:30 בניו יורק).

## התקנה (פעם אחת)

1. **Webhook בדיסקורד:** הגדרות הערוץ ← Integrations ← Webhooks ← New Webhook ← Copy Webhook URL.
2. **ריפו ב-GitHub:** יוצרים ריפו חדש ומעלים אליו את כל הקבצים (כולל התיקייה `.github`).
3. **Secret:** בריפו ← Settings ← Secrets and variables ← Actions ← New repository secret
   שם: `DISCORD_WEBHOOK_URL`, ערך: הכתובת מסעיף 1.
4. **בדיקה:** לשונית Actions ← Market Digest ← Run workflow. תמונה אמורה להגיע לדיסקורד תוך 2-3 דקות.

## עריכת הרשימה

כל השינויים נעשים ב-`watchlist.yaml` — קבוצות, סימולים, ושם המותג.
הסימולים כמו ב-Yahoo Finance (למשל `BRK-B`, `TEVA.TA`).

## מה בתמונה

- **כותרת + הסיפור של היום:** נוצרים אוטומטית מהנתונים (בלי AI): המובילות, היורדות, רוחב שוק (RSP מול S&P), רוטציה בין קבוצות, ותנועות חריגות בביטקוין/נפט/אג״ח.
- **5 עולות / 5 יורדות** מהרשימה שלך.
- **8 משבצות:** S&P 500, NASDAQ, VIX, RUSSELL, RSP, BITCOIN, USOIL, US10Y.
- **צבע רקע** לפי ה-S&P 500: ירוק חזק (≥1%), ירקרק (≥0.25%), ניטרלי, אדמדם (≤-0.25%), אדום (≤-1%).

## הרצה מקומית

```bash
pip install -r requirements.txt
python -m playwright install chromium
python digest.py --demo --no-send   # נתוני דמו
python digest.py --force --no-send  # נתונים אמיתיים, בלי שליחה
```
התמונה נשמרת בתיקייה `out/`.

## הערות

- ריצות מתוזמנות ב-GitHub יכולות להתעכב ב-5 עד 20 דקות.
- בחגים בבורסה ובסופי שבוע לא נשלח כלום.
- GitHub משבית workflows מתוזמנים בריפו שלא היה בו שינוי 60 יום — אם זה קורה, נכנסים ל-Actions ולוחצים Enable.
