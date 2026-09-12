import os, hmac, hashlib, asyncpg
from flask import Flask, request
...

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
DATABASE_URL = os.getenv("DATABASE_URL", "")
OW_PUBLIC = os.getenv("OFFERWALL_PUBLIC_KEY", "")
OW_SECRET = os.getenv("OFFERWALL_SECRET", "")
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "https://watch-earn-arabic.onrender.com")
