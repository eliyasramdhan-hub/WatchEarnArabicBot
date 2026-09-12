import os, sqlite3, hmac, hashlib, threading
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
DB_PATH = os.getenv("DB_PATH", "bot.db")
OW_PUBLIC = os.getenv("OFFERWALL_PUBLIC_KEY", "")
OW_SECRET = os.getenv("OFFERWALL_SECRET", "")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing")

app = Flask(__name__)


def conn():
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    c = conn()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT DEFAULT '',
        balance REAL DEFAULT 0,
        invited_by INTEGER,
        referrals INTEGER DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS transactions (
        tx_id TEXT PRIMARY KEY,
        user_id INTEGER,
        amount REAL,
        status TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""")
    c.commit()
    c.close()


def ensure_user(uid, username="", invited_by=None):
    c = conn()
    exists = c.execute("SELECT user_id FROM users WHERE user_id=?", (uid,)).fetchone()
    if not exists:
        c.execute("INSERT INTO users(user_id,username,invited_by) VALUES(?,?,?)",
                  (uid, username, invited_by))
        if invited_by and invited_by != uid:
            c.execute("UPDATE users SET referrals=referrals+1 WHERE user_id=?", (invited_by,))
    elif username:
        c.execute("UPDATE users SET username=? WHERE user_id=?", (username, uid))
    c.commit()
    c.close()


def get_balance(uid):
    c = conn()
    r = c.execute("SELECT balance FROM users WHERE user_id=?", (uid,)).fetchone()
    c.close()
    return float(r["balance"]) if r else 0.0


def callback_signature(uid, tx, amount):
    raw = f"{uid}:{tx}:{amount}"
    return hmac.new(OW_SECRET.encode(), raw.encode(), hashlib.sha256).hexdigest()


def wall_url(uid):
    # Offerwall.GG signed wall URL: sign sorted query parameters.
    params = f"appId={OW_PUBLIC}&userId={uid}"
    sig = hmac.new(OW_SECRET.encode(), params.encode(), hashlib.sha256).hexdigest()
    return f"https://offerwall.gg/wall/{OW_PUBLIC}?userId={uid}&signature={sig}"


@app.get("/")
def home():
    return "Watch Earn Arabic Bot is running", 200


@app.get("/health")
def health():
    return "OK", 200


@app.get("/offerwall/callback")
def offerwall_callback():
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
        uid_int = int(uid)
        amount_float = float(amount)
    except ValueError:
        return "invalid parameters", 400

    if not OW_SECRET:
        return "secret not configured", 500

    if not hmac.compare_digest(callback_signature(uid, tx, amount), sig):
        return "invalid signature", 403

    c = conn()
    if c.execute("SELECT 1 FROM transactions WHERE tx_id=?", (tx,)).fetchone():
        c.close()
        return "OK", 200

    c.execute("INSERT INTO transactions(tx_id,user_id,amount,status) VALUES(?,?,?,?)",
              (tx, uid_int, amount_float, status))
    c.execute("INSERT OR IGNORE INTO users(user_id,balance) VALUES(?,0)", (uid_int,))
    c.execute("UPDATE users SET balance=balance+? WHERE user_id=?",
              (amount_float, uid_int))
    c.commit()
    c.close()
    return "OK", 200


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    ref = None
    if context.args:
        try:
            ref = int(context.args[0])
        except ValueError:
            pass
    ensure_user(u.id, u.username or "", ref)

    keyboard = [
        ["🎬 المهام", "💰 رصيدي"],
        ["👥 دعوة الأصدقاء", "💸 السحب"],
        ["🏆 المتصدرون", "📞 الدعم"],
    ]
    await update.message.reply_text(
        "👋 أهلاً بك في *شاهد واربح* 💰\n\nاختر من القائمة للبدء.",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
    )


async def router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    ensure_user(u.id, u.username or "")
    text = update.message.text

    if text == "🎬 المهام":
        if not (OW_PUBLIC and OW_SECRET):
            await update.message.reply_text("⚠️ المهام قيد الإعداد حالياً.")
            return
        await update.message.reply_text(
            "🎬 المهام والعروض\n\nأكمل العرض حسب شروطه، وبعد تأكيد التحويل من الشبكة يُضاف رصيدك تلقائياً.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🎯 فتح المهام", url=wall_url(u.id))]
            ])
        )

    elif text == "💰 رصيدي":
        await update.message.reply_text(f"💰 رصيدك الحالي: {get_balance(u.id):g} نقطة")

    elif text == "👥 دعوة الأصدقاء":
        me = await context.bot.get_me()
        link = f"https://t.me/{me.username}?start={u.id}"
        c = conn()
        count = c.execute("SELECT referrals FROM users WHERE user_id=?", (u.id,)).fetchone()[0]
        c.close()
        await update.message.reply_text(
            f"👥 رابط دعوتك:\n{link}\n\nعدد المدعوين: {count}"
        )

    elif text == "💸 السحب":
        await update.message.reply_text(
            "💸 السحب عبر Sham Cash.\n\nأرسل طلبك للإدارة مع المبلغ ورقم Sham Cash."
        )

    elif text == "🏆 المتصدرون":
        c = conn()
        rows = c.execute(
            "SELECT username,balance FROM users ORDER BY balance DESC LIMIT 10"
        ).fetchall()
        c.close()
        lines = ["🏆 المتصدرون:\n"]
        for i, r in enumerate(rows, 1):
            name = f"@{r['username']}" if r["username"] else "مستخدم"
            lines.append(f"{i}. {name} — {float(r['balance']):g} نقطة")
        await update.message.reply_text("\n".join(lines))

    elif text == "📞 الدعم":
        await update.message.reply_text("📞 للدعم: تواصل مع الإدارة.")


async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not ADMIN_ID or update.effective_user.id != ADMIN_ID:
        return
    c = conn()
    users = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    total = c.execute("SELECT COALESCE(SUM(balance),0) FROM users").fetchone()[0]
    c.close()
    await update.message.reply_text(
        f"🛠 لوحة الإدارة\n\nالمستخدمون: {users}\nإجمالي الأرصدة: {float(total):g} نقطة"
    )


init_db()
bot_app = Application.builder().token(BOT_TOKEN).build()
bot_app.add_handler(CommandHandler("start", start))
bot_app.add_handler(CommandHandler("admin", admin))
bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, router))


def run_http():
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")), use_reloader=False)


if __name__ == "__main__":
    threading.Thread(target=run_http, daemon=True).start()
    print("WatchEarnArabicBot is running...")
    bot_app.run_polling(drop_pending_updates=True)
