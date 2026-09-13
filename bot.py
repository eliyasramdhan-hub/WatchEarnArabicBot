import os
import hmac
import hashlib
import asyncpg
import asyncio
import threading

from flask import Flask, request
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ============== الإعدادات ==============
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
DATABASE_URL = os.getenv("DATABASE_URL", "")
OW_PUBLIC = os.getenv("OFFERWALL_PUBLIC_KEY", "")
OW_SECRET = os.getenv("OFFERWALL_SECRET", "")
RENDER_URL = os.getenv(
    "RENDER_EXTERNAL_URL",
    "https://watch-earn-arabic.onrender.com",
)

app = Flask(__name__)

# ============== حلقة أحداث دائمة ==============
_loop = asyncio.new_event_loop()


def _start_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_forever()


threading.Thread(
    target=_start_loop,
    args=(_loop,),
    daemon=True,
).start()

# ============== قاعدة البيانات ==============
_pool = None


async def _get_pool():
    global _pool

    if _pool is None:
        if not DATABASE_URL:
            raise RuntimeError("DATABASE_URL غير موجود في Environment Variables")

        _pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=1,
            max_size=5,
        )

        async with _pool.acquire() as c:
            await c.execute(
                """
                CREATE TABLE IF NOT EXISTS users(
                    user_id BIGINT PRIMARY KEY,
                    username TEXT,
                    balance REAL DEFAULT 0,
                    referrals INTEGER DEFAULT 0
                )
                """
            )

            await c.execute(
                """
                CREATE TABLE IF NOT EXISTS transactions(
                    tx_id TEXT PRIMARY KEY,
                    user_id BIGINT,
                    amount REAL,
                    status TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    return _pool


async def _db_user(uid, name=""):
    p = await _get_pool()

    async with p.acquire() as c:
        await c.execute(
            """
            INSERT INTO users(user_id, username)
            VALUES($1, $2)
            ON CONFLICT(user_id) DO NOTHING
            """,
            uid,
            name,
        )

        if name:
            await c.execute(
                "UPDATE users SET username=$1 WHERE user_id=$2",
                name,
                uid,
            )


async def _db_balance(uid):
    p = await _get_pool()

    async with p.acquire() as c:
        r = await c.fetchrow(
            "SELECT balance, referrals FROM users WHERE user_id=$1",
            uid,
        )

        if r:
            return float(r["balance"]), int(r["referrals"])

        return 0.0, 0


async def _db_top():
    p = await _get_pool()

    async with p.acquire() as c:
        return await c.fetch(
            """
            SELECT username, balance
            FROM users
            ORDER BY balance DESC
            LIMIT 10
            """
        )


async def _db_rank(uid):
    p = await _get_pool()

    async with p.acquire() as c:
        r = await c.fetchrow(
            """
            SELECT COUNT(*) + 1 AS rank
            FROM users
            WHERE balance > (
                SELECT balance
                FROM users
                WHERE user_id=$1
            )
            """,
            uid,
        )

        return int(r["rank"]) if r else 0


# ============== التوقيع ==============
def sign(uid, tx, amount):
    return hmac.new(
        OW_SECRET.encode(),
        f"{uid}:{tx}:{amount}".encode(),
        hashlib.sha256,
    ).hexdigest()


def wall(uid):
    return (
        f"https://offerwall.gg/wall/{OW_PUBLIC}"
        f"?userId={uid}"
        f"&signature={sign(str(uid), '', '')}"
    )


# ============== لوحة المفاتيح ==============
def main_keyboard():
    kb = [
        ["المهام", "رصيدي"],
        ["دعوة الأصدقاء", "السحب"],
        ["المتصدرون", "الدعم"],
    ]

    return ReplyKeyboardMarkup(
        kb,
        resize_keyboard=True,
    )


# ============== معالجات الأوامر ==============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        u = update.effective_user

        if not u:
            return

        await _db_user(
            u.id,
            u.username or "",
        )

        name = u.first_name or "صديقي"

        await update.message.reply_text(
            f"مرحباً {name} في شاهد واربح 💰\n\n"
            "هنا يمكنك كسب النقود عبر إكمال المهام والعروض.\n"
            "كل مهمة تكملها تضيف رصيداً إلى حسابك.\n\n"
            "اختر من الأزرار أدناه:",
            reply_markup=main_keyboard(),
        )

    except Exception as e:
        print(f"START ERROR: {e}")

        if update.message:
            await update.message.reply_text(
                f"حدث خطأ أثناء تشغيل البوت:\n{str(e)}"
            )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.reply_text(
            "📋 أوامر البوت:\n\n"
            "/start — بدء البوت\n"
            "/tasks — المهام والعروض\n"
            "/balance — عرض رصيدك\n"
            "/referral — رابط دعوة الأصدقاء\n"
            "/withdraw — طلب السحب\n"
            "/top — المتصدرون\n"
            "/support — الدعم\n"
            "/help — قائمة الأوامر",
            reply_markup=main_keyboard(),
        )

    except Exception as e:
        print(f"HELP ERROR: {e}")


async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        u = update.effective_user

        await _db_user(
            u.id,
            u.username or "",
        )

        bal, refs = await _db_balance(u.id)
        rank = await _db_rank(u.id)

        await update.message.reply_text(
            f"💰 رصيدك الحالي: {bal:g} نقطة\n"
            f"👥 عدد إحالاتك: {refs}\n"
            f"🏆 ترتيبك: {rank}"
        )

    except Exception as e:
        print(f"BALANCE ERROR: {e}")
        await update.message.reply_text(
            f"حدث خطأ: {str(e)}"
        )


async def tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        u = update.effective_user

        await _db_user(
            u.id,
            u.username or "",
        )

        if not (OW_PUBLIC and OW_SECRET):
            await update.message.reply_text(
                "المهام قيد الإعداد حالياً."
            )
            return

        await update.message.reply_text(
            "اختر مهمة وأكملها، وبعد التأكيد يُضاف الرصيد تلقائياً.",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "فتح المهام والعروض",
                            url=wall(u.id),
                        )
                    ]
                ]
            ),
        )

    except Exception as e:
        print(f"TASKS ERROR: {e}")
        await update.message.reply_text(
            f"حدث خطأ: {str(e)}"
        )


async def referral_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        u = update.effective_user

        await _db_user(
            u.id,
            u.username or "",
        )

        await update.message.reply_text(
            "👥 رابط دعوتك الخاص:\n\n"
            f"https://t.me/WatchEarnArabicBot?start={u.id}\n\n"
            "شارك الرابط مع أصدقائك."
        )

    except Exception as e:
        print(f"REFERRAL ERROR: {e}")
        await update.message.reply_text(
            f"حدث خطأ: {str(e)}"
        )


async def withdraw_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        u = update.effective_user

        await _db_user(
            u.id,
            u.username or "",
        )

        bal, _ = await _db_balance(u.id)

        await update.message.reply_text(
            "💸 السحب عبر Sham Cash.\n\n"
            "الحد الأدنى للسحب: 5,000 نقطة\n"
            f"رصيدك الحالي: {bal:g} نقطة\n\n"
            "لطلب السحب، تواصل مع الإدارة."
        )

    except Exception as e:
        print(f"WITHDRAW ERROR: {e}")
        await update.message.reply_text(
            f"حدث خطأ: {str(e)}"
        )


async def top_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        rows = await _db_top()

        if not rows:
            await update.message.reply_text(
                "لا يوجد متصدرون بعد."
            )
            return

        s = "🏆 قائمة المتصدرين:\n\n"

        for i, r in enumerate(rows, 1):
            name = (
                f"@{r['username']}"
                if r["username"]
                else "مستخدم"
            )

            s += f"{i}. {name} — {float(r['balance']):g}\n"

        await update.message.reply_text(s)

    except Exception as e:
        print(f"TOP ERROR: {e}")
        await update.message.reply_text(
            f"حدث خطأ: {str(e)}"
        )


async def support_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📞 للدعم: تواصل مع الإدارة مباشرة."
    )


# ============== معالج أزرار البوت ==============
async def router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        u = update.effective_user

        if not u or not update.message:
            return

        await _db_user(
            u.id,
            u.username or "",
        )

        t = update.message.text

        if t == "المهام":
            await tasks_command(update, context)

        elif t == "رصيدي":
            await balance_command(update, context)

        elif t == "دعوة الأصدقاء":
            await referral_command(update, context)

        elif t == "السحب":
            await withdraw_command(update, context)

        elif t == "المتصدرون":
            await top_command(update, context)

        elif t == "الدعم":
            await support_command(update, context)

        else:
            await update.message.reply_text(
                "اختر من الأزرار أدناه:",
                reply_markup=main_keyboard(),
            )

    except Exception as e:
        print(f"ROUTER ERROR: {e}")

        if update.message:
            await update.message.reply_text(
                f"حدث خطأ: {str(e)}"
            )


# ============== Application مشترك ==============
_bot_app = None
_init_lock = threading.Lock()


def _get_bot_app():
    global _bot_app

    if _bot_app is None:
        with _init_lock:
            if _bot_app is None:
                if not BOT_TOKEN:
                    raise RuntimeError(
                        "BOT_TOKEN غير موجود في Environment Variables"
                    )

                _bot_app = (
                    Application.builder()
                    .token(BOT_TOKEN)
                    .build()
                )

                _bot_app.add_handler(
                    CommandHandler("start", start)
                )

                _bot_app.add_handler(
                    CommandHandler("help", help_command)
                )

                _bot_app.add_handler(
                    CommandHandler("balance", balance_command)
                )

                _bot_app.add_handler(
                    CommandHandler("tasks", tasks_command)
                )

                _bot_app.add_handler(
                    CommandHandler("referral", referral_command)
                )

                _bot_app.add_handler(
                    CommandHandler("withdraw", withdraw_command)
                )

                _bot_app.add_handler(
                    CommandHandler("top", top_command)
                )

                _bot_app.add_handler(
                    CommandHandler("support", support_command)
                )

                _bot_app.add_handler(
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        router,
                    )
                )

    return _bot_app


async def _ensure_init():
    bot_app = _get_bot_app()

    if not bot_app.initialized:
        await bot_app.initialize()

        # تسجيل الأوامر في قائمة Telegram
        await bot_app.bot.set_my_commands(
            [
                ("start", "بدء البوت"),
                ("tasks", "المهام والعروض"),
                ("balance", "عرض رصيدك"),
                ("referral", "رابط دعوة الأصدقاء"),
                ("withdraw", "طلب السحب"),
                ("top", "المتصدرون"),
                ("support", "الدعم"),
                ("help", "قائمة الأوامر"),
            ]
        )

        # التأكد من أن Webhook مضبوط على رابط Render الصحيح
        webhook_url = f"{RENDER_URL.rstrip('/')}/telegram"

        await bot_app.bot.set_webhook(
            url=webhook_url,
            allowed_updates=Update.ALL_TYPES,
        )

        print(f"Webhook set to: {webhook_url}")
        print("Telegram bot initialized successfully")

    return bot_app


# ============== Flask Routes ==============
@app.get("/")
def home():
    return "Watch Earn Arabic Bot is running", 200


@app.get("/health")
def health():
    return "OK", 200


@app.route("/telegram", methods=["POST"])
def telegram_webhook():
    try:
        data = request.get_json(force=True)

        if not data:
            return "No update", 400

        future = asyncio.run_coroutine_threadsafe(
            _process_update(data),
            _loop,
        )

        # ننتظر التنفيذ حتى يظهر أي خطأ حقيقي في Render
        future.result(timeout=20)

        return "OK", 200

    except Exception as e:
        print(f"WEBHOOK ERROR: {e}")
        return f"Error: {str(e)}", 500


async def _process_update(data):
    try:
        bot_app = await _ensure_init()

        update = Update.de_json(
            data,
            bot_app.bot,
        )

        if update is None:
            print("Received empty/invalid Telegram update")
            return

        await bot_app.process_update(update)

        print(
            f"Telegram update processed: "
            f"{update.update_id}"
        )

    except Exception as e:
        print(f"PROCESS UPDATE ERROR: {e}")
        raise


# ============== Offerwall Callback ==============
@app.get("/offerwall/callback")
def callback():
    try:
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
            int(uid)
            float(amount)
        except Exception:
            return "invalid parameters", 400

        if not hmac.compare_digest(
            sign(uid, tx, amount),
            sig,
        ):
            return "invalid signature", 403

        future = asyncio.run_coroutine_threadsafe(
            _handle_callback(
                uid,
                amount,
                tx,
                status,
            ),
            _loop,
        )

        future.result(timeout=20)

        return "OK", 200

    except Exception as e:
        print(f"CALLBACK ERROR: {e}")
        return f"Error: {str(e)}", 500


async def _handle_callback(uid, amount, tx, status):
    p = await _get_pool()

    async with p.acquire() as c:
        exists = await c.fetchrow(
            "SELECT 1 FROM transactions WHERE tx_id=$1",
            tx,
        )

        if exists:
            return

        await c.execute(
            """
            INSERT INTO transactions(
                tx_id,
                user_id,
                amount,
                status
            )
            VALUES($1, $2, $3, $4)
            """,
            tx,
            int(uid),
            float(amount),
            status,
        )

        await c.execute(
            """
            INSERT INTO users(user_id, balance)
            VALUES($1, 0)
            ON CONFLICT(user_id) DO NOTHING
            """,
            int(uid),
        )

        await c.execute(
            """
            UPDATE users
            SET balance=balance+$1
            WHERE user_id=$2
            """,
            float(amount),
            int(uid),
        )

        print(
            f"Offerwall callback: user={uid}, "
            f"amount={amount}, tx={tx}, status={status}"
        )
