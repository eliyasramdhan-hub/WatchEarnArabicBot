import os, hmac, hashlib, asyncpg
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
DATABASE_URL = os.getenv("DATABASE_URL", "")
OW_PUBLIC = os.getenv("OFFERWALL_PUBLIC_KEY", "")
OW_SECRET = os.getenv("OFFERWALL_SECRET", "")
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "https://watch-earn-arabic.onrender.com")

app = Flask(__name__)
pool = None

# ============== قاعدة البيانات ==============

async def init_db():
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
    async with pool.acquire() as c:
        await c.execute("""
            CREATE TABLE IF NOT EXISTS users(
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                balance REAL DEFAULT 0,
                referrals INTEGER DEFAULT 0
            )
        """)
        await c.execute("""
            CREATE TABLE IF NOT EXISTS transactions(
                tx_id TEXT PRIMARY KEY,
                user_id BIGINT,
                amount REAL,
                status TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

async def db_user(uid, name=""):
    async with pool.acquire() as c:
        await c.execute(
            "INSERT INTO users(user_id,username) VALUES($1,$2) ON CONFLICT(user_id) DO NOTHING",
            uid, name
        )
        if name:
            await c.execute("UPDATE users SET username=$1 WHERE user_id=$2", name, uid)

async def db_balance(uid):
    async with pool.acquire() as c:
        r = await c.fetchrow("SELECT balance FROM users WHERE user_id=$1", uid)
        return float(r["balance"]) if r else 0.0

async def db_top():
    async with pool.acquire() as c:
        return await c.fetch("SELECT username,balance FROM users ORDER BY balance DESC LIMIT 10")

# ============== التوقيع ==============

def sign(uid, tx, amount):
    return hmac.new(OW_SECRET.encode(), f"{uid}:{tx}:{amount}".encode(), hashlib.sha256).hexdigest()

def wall(uid):
    return f"https://offerwall.gg/wall/{OW_PUBLIC}?userId={uid}&signature={sign(str(uid),'','')}"

# ============== Flask Routes ==============

@app.get("/")
def home():
    return "Watch Earn Arabic Bot is running", 200

@app.get("/health")
def health():
    return "OK", 200

@app.route("/telegram", methods=["POST"])
async def telegram_webhook():
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, router))
    update = Update.de_json(request.get_json(force=True), application.bot)
    await application.initialize()
    await application.process_update(update)
    return "OK", 200

@app.get("/offerwall/callback")
async def callback():
    uid = request.args.get("user", "")
    amount = request.args.get("amount", "")
    tx = request.args.get("tx", "")
    status = request.args.get("status", "")
    sig = request.args.get("sig", "")

    if request.args.get("test") == "1":
        return "OK", 200
    if not all((uid, amount, tx, sig)):
        return "missing parameters", 400
    try:
        int(uid); float(amount)
    except:
        return "invalid parameters", 400
    if not hmac.compare_digest(sign(uid, tx, amount), sig):
        return "invalid signature", 403

    async with pool.acquire() as c:
        exists = await c.fetchrow("SELECT 1 FROM transactions WHERE tx_id=$1", tx)
        if exists:
            return "OK", 200
        await c.execute(
            "INSERT INTO transactions(tx_id,user_id,amount,status) VALUES($1,$2,$3,$4)",
            tx, int(uid), float(amount), status
        )
        await c.execute(
            "INSERT INTO users(user_id,balance) VALUES($1,0) ON CONFLICT(user_id) DO NOTHING",
            int(uid)
        )
        await c.execute(
            "UPDATE users SET balance=balance+$1 WHERE user_id=$2",
            float(amount), int(uid)
        )
    return "OK", 200

@app.get("/setwebhook")
async def set_webhook():
    application = Application.builder().token(BOT_TOKEN).build()
    webhook_url = f"{RENDER_URL}/telegram"
    await application.bot.set_webhook(url=webhook_url, drop_pending_updates=True)
    return f"Webhook set to {webhook_url}", 200

# ============== معالجات البوت ==============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    await db_user(u.id, u.username or "")
    kb = [["🎬 المهام", "💰 رصيدي"], ["👥 دعوة الأصدقاء", "💸 السحب"], ["🏆 المتصدرون", "📞 الدعم"]]
    await update.message.reply_text(
        "أهلاً بك في شاهد واربح 💰\nاختر من القائمة:",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
    )

async def router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    await db_user(u.id, u.username or "")
    t = update.message.text

    if t == "🎬 المهام":
        if not (OW_PUBLIC and OW_SECRET):
            await update.message.reply_text("⚠️ المهام قيد الإعداد حالياً.")
            return
        await update.message.reply_text(
            "🎬 اختر مهمة وأكملها، وبعد التأكيد يُضاف الرصيد تلقائياً.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎯 المهام والعروض", url=wall(u.id))]])
        )
    elif t == "💰 رصيدي":
        b = await db_balance(u.id)
        await update.message.reply_text(f"💰 رصيدك: {b:g} نقطة")
    elif t == "👥 دعوة الأصدقاء":
        await update.message.reply_text(f"👥 رابط دعوتك:\nhttps://t.me/WatchEarnArabicBot?start={u.id}")
    elif t == "💸 السحب":
        await update.message.reply_text("💸 السحب عبر Sham Cash.\nأرسل طلبك للدعم.")
    elif t == "🏆 المتصدرون":
        rows = await db_top()
        s = "🏆 المتصدرون:\n" + "".join(
            f"{i}. @{r['username'] or 'مستخدم'} — {float(r['balance']):g}\n"
            for i, r in enumerate(rows, 1)
        )
        await update.message.reply_text(s)
    elif t == "📞 الدعم":
        await update.message.reply_text("📞 للدعم: تواصل مع الإدارة.")

# ============== تشغيل Flask فقط (Render سيستخدم gunicorn) ==============

if __name__ == "__main__":
    import asyncio
    asyncio.run(init_db())
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")), use_reloader=False)
