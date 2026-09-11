# WatchEarnArabicBot

نسخة أولية من بوت «شاهد واربح»:
- قائمة رئيسية
- رصيد
- إحالة الأصدقاء
- طلبات سحب
- SQLite
- لوحة إدارة بسيطة
- جاهز لاحقًا لربط Offerwall/API وPostback

## التشغيل على الكمبيوتر أو الاستضافة

1. ثبّت Python 3.11 أو أحدث.
2. افتح مجلد المشروع.
3. ثبّت المكتبات:
   `pip install -r requirements.txt`
4. أنشئ متغيري البيئة:
   `BOT_TOKEN` = التوكن الجديد من BotFather
   `ADMIN_ID` = رقم Telegram user ID الخاص بك
5. شغّل:
   `python bot.py`

### Windows PowerShell
`$env:BOT_TOKEN="TOKEN_HERE"`
`$env:ADMIN_ID="123456789"`
`python bot.py`

### Linux / VPS
`export BOT_TOKEN="TOKEN_HERE"`
`export ADMIN_ID="123456789"`
`python3 bot.py`

## مهم
لا تضع التوكن داخل ملف منشور أو ترسله لأي شخص.
النسخة الحالية لا تدّعي احتساب مشاهدات مدفوعة تلقائيًا. يجب أولًا ربط مصدر مهام/إعلانات يسمح بهذا النوع من الترافيك، ثم نضيف الـAPI والـpostback والتحقق من الإكمال.
