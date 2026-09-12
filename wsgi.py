import asyncio
from bot import app, init_db

# إنشاء حلقة أحداث جديدة وتثبيتها
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

# تهيئة قاعدة البيانات في نفس الحلقة
loop.run_until_complete(init_db())

# ربط Flask بالحلقة
application = app
