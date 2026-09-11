import os
import sqlite3
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
DB_PATH = os.getenv("DB_PATH", "bot.db")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing. Put it in the environment before starting.")

db = sqlite3.connect(DB_PATH, check_same_thread=False)
db.execute("""CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    balance REAL NOT NULL DEFAULT 0,
    invited_by INTEGER,
    joined_at TEXT NOT NULL
)""")
db.execute("""CREATE TABLE IF NOT EXISTS withdrawals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    amount REAL NOT NULL,
    sham_cash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL
)""")
db.commit()

def ensure_user(user):
    row = db.execute("SELECT user_id FROM users WHERE user_id=?", (user.id,)).fetchone()
    if not row:
        db.execute(
            "INSERT INTO users(user_id, username, joined_at) VALUES(?,?,?)",
            (user.id, user.username or "", datetime.utcnow().isoformat())
        )
        db.commit()

def main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 المهام", callback_data="tasks"),
         InlineKeyboardButton("💰 رصيدي", callback_data="balance")],
        [InlineKeyboardButton("👥 دعوة الأصدقاء", callback_data="ref"),
         InlineKeyboardButton("💸 السحب", callback_data="withdraw")],
        [InlineKeyboardButton("🏆 المتصدرون", callback_data="leaders"),
         InlineKeyboardButton("📞 الدعم", callback_data="support")]
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user(user)

    # /start REFERRER_ID
    if context.args:
        try:
            referrer = int(context.args[0])
            if referrer != user.id:
                current = db.execute("SELECT invited_by FROM users WHERE user_id=?", (user.id,)).fetchone()
                if current and current[0] is None:
                    exists = db.execute("SELECT 1 FROM users WHERE user_id=?", (referrer,)).fetchone()
                    if exists:
                        db.execute("UPDATE users SET invited_by=? WHERE user_id=?", (referrer, user.id))
                        db.commit()
        except ValueError:
            pass

    await update.message.reply_text(
        "👋 أهلاً بك في *شاهد واربح* 💰\n\n"
        "اختر من القائمة للبدء.\n"
        "ملاحظة: المهام المدفوعة لن تُحتسب إلا بعد ربط مصدر إعلانات/مهام حقيقي.",
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )

async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user = q.from_user
    ensure_user(user)

    if q.data == "balance":
        balance = db.execute("SELECT balance FROM users WHERE user_id=?", (user.id,)).fetchone()[0]
        await q.edit_message_text(
            f"💰 *رصيدك الحالي:* `{balance:.4f}`\n\n"
            "يمكنك طلب السحب من زر 💸 السحب.",
            parse_mode="Markdown", reply_markup=main_keyboard()
        )

    elif q.data == "tasks":
        await q.edit_message_text(
            "🎬 *المهام*\n\n"
            "لا توجد مهام مدفوعة مفعّلة حاليًا.\n\n"
            "هذه الواجهة جاهزة لربط Offerwall/API أو نظام مهام خاص بك.",
            parse_mode="Markdown", reply_markup=main_keyboard()
        )

    elif q.data == "ref":
        me = await context.bot.get_me()
        link = f"https://t.me/{me.username}?start={user.id}"
        count = db.execute("SELECT COUNT(*) FROM users WHERE invited_by=?", (user.id,)).fetchone()[0]
        await q.edit_message_text(
            f"👥 *رابط دعوتك:*\n{link}\n\n"
            f"عدد المدعوين: *{count}*\n"
            "سنضيف مكافأة الإحالة عند تحديد قيمة العمولة.",
            parse_mode="Markdown", reply_markup=main_keyboard()
        )

    elif q.data == "withdraw":
        await q.edit_message_text(
            "💸 *طلب السحب*\n\n"
            "النسخة الأولى تستخدم طلبات سحب يدوية.\n"
            "اكتب لاحقًا: `/withdraw المبلغ رقم_شام_كاش`\n\n"
            "مثال:\n`/withdraw 2 09xxxxxxxx`",
            parse_mode="Markdown", reply_markup=main_keyboard()
        )

    elif q.data == "leaders":
        rows = db.execute(
            "SELECT username, balance FROM users ORDER BY balance DESC LIMIT 10"
        ).fetchall()
        text = "🏆 *المتصدرون*\n\n"
        for i, (username, balance) in enumerate(rows, 1):
            name = f"@{username}" if username else "مستخدم"
            text += f"{i}. {name} — {balance:.4f}\n"
        await q.edit_message_text(text, parse_mode="Markdown", reply_markup=main_keyboard())

    elif q.data == "support":
        await q.edit_message_text(
            "📞 *الدعم*\n\n"
            "ضع حساب الدعم الخاص بك في متغير SUPPORT_USERNAME داخل الكود قبل الإطلاق.",
            parse_mode="Markdown", reply_markup=main_keyboard()
        )

async def withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user(user)
    if len(context.args) != 2:
        await update.message.reply_text("الصيغة: /withdraw المبلغ رقم_شام_كاش")
        return
    try:
        amount = float(context.args[0])
        sham = context.args[1]
    except ValueError:
        await update.message.reply_text("المبلغ يجب أن يكون رقمًا.")
        return
    if amount <= 0:
        await update.message.reply_text("المبلغ يجب أن يكون أكبر من صفر.")
        return

    balance = db.execute("SELECT balance FROM users WHERE user_id=?", (user.id,)).fetchone()[0]
    if amount > balance:
        await update.message.reply_text(f"رصيدك غير كافٍ. رصيدك: {balance:.4f}")
        return

    db.execute("UPDATE users SET balance=balance-? WHERE user_id=?", (amount, user.id))
    db.execute(
        "INSERT INTO withdrawals(user_id, amount, sham_cash, created_at) VALUES(?,?,?,?)",
        (user.id, amount, sham, datetime.utcnow().isoformat())
    )
    db.commit()

    await update.message.reply_text("✅ تم تسجيل طلب السحب، وسيتم مراجعته من الإدارة.")

    if ADMIN_ID:
        await context.bot.send_message(
            ADMIN_ID,
            f"💸 طلب سحب جديد\n"
            f"المستخدم: {user.id}\n"
            f"المبلغ: {amount}\n"
            f"شام كاش: {sham}"
        )

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID or not ADMIN_ID:
        return
    users = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    pending = db.execute("SELECT COUNT(*) FROM withdrawals WHERE status='pending'").fetchone()[0]
    await update.message.reply_text(
        f"🛠 لوحة الإدارة\n\nالمستخدمون: {users}\nطلبات السحب المعلقة: {pending}"
    )

def run():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("withdraw", withdraw))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CallbackQueryHandler(buttons))
    print("WatchEarnArabicBot is running...")
    app.run_polling()

if __name__ == "__main__":
    run()
