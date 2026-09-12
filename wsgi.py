
import asyncio
from bot import app, init_db  # تأكد من أن هذه الاستيرادات صحيحة من ملف bot.py

# تهيئة قاعدة البيانات عند بدء التشغيل
try:
    loop = asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

# استدعاء دالة التهيئة
loop.run_until_complete(init_db())

# تشغيل التطبيق (هذا الجزء مفقود في كودك ويجب إضافته)
if __name__ == "__main__":
    app.run() 
