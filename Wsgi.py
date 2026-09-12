import asyncio
from bot import app, init_db

# تهيئة قاعدة البيانات عند بدء تشغيل الخدمة
asyncio.get_event_loop().run_until_complete(init_db())

# gunicorn سيبحث عن "app"
application = app
