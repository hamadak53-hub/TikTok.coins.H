# HAMO STORE

بوت تيليجرام لمتجر شحن TikTok وطلبات الحسابات، مبني باستخدام Python و aiogram 3 وSQLite.

## التشغيل
1. استخدم Python 3.10 أو أحدث.
2. ثبّت المكتبات: `pip install -r requirements.txt`
3. اضبط متغيرات البيئة:
   - `BOT_TOKEN`: توكن البوت من BotFather.
   - `ADMIN_IDS`: Telegram user ID للأدمن، ويمكن وضع أكثر من رقم مفصولاً بفواصل.
   - `DB_PATH` اختياري لمسار قاعدة البيانات.
4. ضع أسعار البيع الحقيقية في `catalog.py`؛ السعر صفر يعطّل الباقة.
5. شغّل من مجلد المشروع: `python bot.py`

## Render
أنشئ Background Worker:
- Build Command: `pip install -r requirements.txt`
- Start Command: `python bot.py`
- Environment: أضف `BOT_TOKEN` و `ADMIN_IDS` كمتغيرات سرية.

## ملاحظات
- أوقف أي نسخة قديمة تستخدم نفس BOT_TOKEN قبل تشغيل نسخة جديدة.
- استقبال الإيصالات ومراجعتها يدوي؛ لا يوجد مورد شحن تلقائي مربوط حالياً.
- لا تضع BOT_TOKEN داخل ملفات GitHub.
- SQLite على التخزين المؤقت قد تفقد بياناتها عند إعادة إنشاء الخدمة؛ استخدم تخزيناً دائماً أو قاعدة بيانات خارجية لحفظ الطلبات.
