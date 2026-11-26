# HAMO STORE

مشروع بوت تيليجرام مبني على aiogram 3 وSQLite.

## الملفات
- `app/bot.py`: تشغيل البوت والوظائف.
- `app/config.py`: إعدادات البيئة.
- `app/db.py`: قاعدة البيانات.
- `app/catalog.py`: باقات الشحن وأسعارها.
- `requirements.txt`: المكتبات.

## الإعداد المحلي
1. ثبّت Python 3.11 أو أحدث.
2. نفّذ: `pip install -r requirements.txt`
3. عيّن متغيرات البيئة:
   - `BOT_TOKEN`: توكن البوت من BotFather (لا تشاركه مع أحد).
   - `ADMIN_IDS`: رقم Telegram user ID للأدمن. يمكن إضافة أكثر من رقم مفصولاً بفواصل.
4. عدّل الأسعار في `app/catalog.py` وضع أرقاماً أكبر من صفر.
5. شغّل: `python -m app.bot`

## Render
أنشئ Background Worker، واجعل:
- Build Command: `pip install -r requirements.txt`
- Start Command: `python -m app.bot`
وأضف `BOT_TOKEN` و`ADMIN_IDS` في Environment.

## تنبيهات مهمة
- شغّل نسخة polling واحدة فقط من البوت. أوقف أي خدمة/نسخة قديمة تستخدم نفس التوكن.
- SQLite داخل نظام ملفات Render المؤقت قد تفقد بياناته عند إعادة إنشاء الخدمة. استخدم قرصاً دائماً أو PostgreSQL إذا كانت البيانات مهمة.
- أسعار `catalog.py` الحالية صفر كقيمة تعطيل؛ ضع أسعارك الحقيقية قبل فتح البيع.
- التحويلات البنكية والبوابات الإلكترونية غير مفعلة؛ المتاح في هذا الإصدار فودافون كاش وإنستا باي مع مراجعة يدوية للإيصال.
