import os, hmac, hashlib, asyncpg
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

# ============== الإعدادات ==============
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
DATABASE_URL = os.getenv("DATABASE_URL", "")
OW_PUBLIC = os.getenv("OFFERWALL_PUBLIC_KEY", "")
OW_SECRET = os.getenv("OFFERWALL_SECRET", "")
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "https://watch-earn-arabic.onrender.com")

app = Flask(__name__)

# ============== قاعدة البيانات ==============
_pool = None

async def get_pool():
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
        async with _pool.acquire() as c:
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
    return _pool

async def db_user(uid, name=""):
    p = await get_pool()
    async with p.acquire() as c:
        await c.execute(
            "INSERT INTO users(user_id,username) VALUES($1,$2) ON CONFLICT(user_id) DO NOTHING",
            uid, name
        )
        if name:
            await c.execute("UPDATE users SET username=$1 WHERE user_id=$2", name, uid)

async def db_balance(uid):
    p = await get_pool()
    async with p.acquire() as c:
        r = await c.fetchrow("SELECT balance, referrals FROM users WHERE user_id=$1", uid)
        return (float(r["balance"]), int(r["referrals"])) if r else (0.0, 0)

async def db_top():
    p = await get_pool()
    async with p.acquire() as c:
        return await c.fetch("SELECT username,balance FROM users ORDER BY balance DESC LIMIT 10")

async def db_rank(uid):
    p = await get_pool()
    async with p.acquire() as c:
        r = await c.fetchrow("""
            SELECT COUNT(*) + 1 AS rank FROM users 
            WHERE balance > (SELECT balance FROM users WHERE user_id=$1)
        """, uid)
        return int(r["rank"]) if r else 0

# ============== التوقيع ==============
def sign(uid, tx, amount):
    return hmac.new(OW_SECRET.encode(), f"{uid}:{tx}:{amount}".encode(), hashlib.sha256).hexdigest()

def wall(uid):
    return f"https://offerwall.gg/wall/{OW_PUBLIC}?userId={uid}&signature={sign(str(uid),'','')}"

# ============== Application واحد مشترك ==============
_bot_app = None

def get_bot_app():
    global _bot_app
    if _bot_app is None:
        _bot_app = Application.builder().token(BOT_TOKEN).build()
        _bot_app.add_handler(CommandHandler("start", start))
        _bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, router))
    return _bot_app

# ============== Flask Routes ==============
@app.get("/")
def home():
    return "Watch Earn Arabic Bot is running", 200

@app.get("/health")
def health():
    return "OK", 200

@app.route("/telegram", methods=["POST"])
async def telegram_webhook():
    bot_app = get_bot_app()
    try:
        await bot_app.initialize()
    except Exception:
        pass
    update = Update.de_json(request.get_json(force=True), bot_app.bot)
    await bot_app.process_update(update)
    return "OK", 200

@app.get("/offerwall/callback")
async def callback():
    p = await get_pool()
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

    async with p.acquire() as c:
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

# ============== لوحة المفاتيح ==============
def main_keyboard():
    kb = [
        ["المهام", "رصيدي"],
        ["دعوة الأصدقاء", "السحب"],
        ["المتصدرون", "الدعم"]
    ]
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

# ============== معالجات البوت ==============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        u = update.effective_user
        await db_user(u.id, u.username or "")
        name = u.first_name or "صديقي"
        await update.message.reply_text(
            f"مرحباً {name} في شاهد واربح 💰\n\n"
            f"هنا يمكنك كسب النقود عبر إكمال المهام والعروض.\n"
            f"كل مهمة تكملها تضيف رصيداً إلى حسابك.\n\n"
            f"اختر من الأزرار أدناه:",
            reply_markup=main_keyboard()
        )
    except Exception as e:
        await update.message.reply_text(f"خطأ: {str(e)}")

async def router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        u = update.effective_user
        await db_user(u.id, u.username or "")
        t = update.message.text

        if t == "المهام":
            if not (OW_PUBLIC and OW_SECRET):
                await update.message.reply_text("المهام قيد الإعداد حالياً.")
                return
            await update.message.reply_text(
                "اختر مهمة وأكملها، وبعد التأكيد يُضاف الرصيد تلقائياً.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("فتح المهام والعروض", url=wall(u.id))
                ]])
            )
        elif t == "رصيدي":
            bal, refs = await db_balance(u.id)
            rank = await db_rank(u.id)
            await update.message.reply_text(
                f"💰 رصيدك الحالي: {bal:g} نقطة\n"
                f"👥 عدد إحالاتك: {refs}\n"
                f"🏆 ترتيبك: {rank}"
            )
        elif t == "دعوة الأصدقاء":
            link = f"https://t.me/WatchEarnArabicBot?start={u.id}"
            await update.message.reply_text(
                f"👥 رابط دعوتك الخاص:\n\n{link}\n\n"
                f"شارك الرابط مع أصدقائك."
            )
        elif t == "السحب":
            bal, _ = await db_balance(u.id)
            await update.message.reply_text(
                f"💸 السحب عبر Sham Cash.\n\n"
                f"الحد الأدنى للسحب: 5,000 نقطة\n"
                f"رصيدك الحالي: {bal:g} نقطة\n\n"
                f"لطلب السحب، تواصل مع الإدارة."
            )
        elif t == "المتصدرون":
            rows = await db_top()
            if not rows:
                await update.message.reply_text("لا يوجد متصدرون بعد.")
                return
            s = "🏆 قائمة المتصدرين:\n\n"
            for i, r in enumerate(rows, 1):
                name = f"@{r['username']}" if r['username'] else "مستخدم"
                s += f"{i}. {name} — {float(r['balance']):g}\n"
            await update.message.reply_text(s)
        elif t == "الدعم":
            await update.message.reply_text(
                "📞 للدعم والاستفسارات:\n\nتواصل مع الإدارة مباشرة."
            )
        else:
            await update.message.reply_text("اختر من الأزرار أدناه:", reply_markup=main_keyboard())

    except Exception as e:
        await update.message.reply_text(f"حدث خطأ: {str(e)}")
