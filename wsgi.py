import asyncio
from bot import app, init_db

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
loop.run_until_complete(init_db())

application = app
