import asyncio
from bot import app, init_db

# تهيئة قاعدة البيانات عند بدء التشغيل
try:
    loop = asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

loop.run_until_complete(init_db())

application = app
