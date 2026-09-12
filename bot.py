import os, sqlite3, hmac, hashlib, threading
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

BOT_TOKEN=os.getenv("BOT_TOKEN")
ADMIN_ID=int(os.getenv("ADMIN_ID","0"))
DB_PATH=os.getenv("DB_PATH","bot.db")
OW_PUBLIC=os.getenv("OFFERWALL_PUBLIC_KEY","")
OW_SECRET=os.getenv("OFFERWALL_SECRET","")
app=Flask(__name__)

def conn():
    c=sqlite3.connect(DB_PATH,check_same_thread=False); c.row_factory=sqlite3.Row; return c

def init():
    c=conn()
    c.execute("CREATE TABLE IF NOT EXISTS users(user_id INTEGER PRIMARY KEY,username TEXT,balance REAL DEFAULT 0,referrals INTEGER DEFAULT 0)")
    c.execute("CREATE TABLE IF NOT EXISTS transactions(tx_id TEXT PRIMARY KEY,user_id INTEGER,amount REAL,status TEXT,created_at DATETIME DEFAULT CURRENT_TIMESTAMP)")
    c.commit(); c.close()

def user(uid,name=""):
    c=conn(); c.execute("INSERT OR IGNORE INTO users(user_id,username) VALUES(?,?)",(uid,name))
    if name: c.execute("UPDATE users SET username=? WHERE user_id=?",(name,uid))
    c.commit(); c.close()

def balance(uid):
    c=conn(); r=c.execute("SELECT balance FROM users WHERE user_id=?",(uid,)).fetchone(); c.close()
    return float(r["balance"]) if r else 0

def sign(uid,tx,amount):
    return hmac.new(OW_SECRET.encode(),f"{uid}:{tx}:{amount}".encode(),hashlib.sha256).hexdigest()

def wall(uid):
    return f"https://offerwall.gg/wall/{OW_PUBLIC}?userId={uid}&signature={sign(str(uid),'','')}"

@app.get("/")
def home(): return "Watch Earn Arabic Bot is running",200

@app.get("/health")
def health(): return "OK",200

@app.get("/offerwall/callback")
def callback():
    uid=request.args.get("user",""); amount=request.args.get("amount",""); tx=request.args.get("tx","")
    status=request.args.get("status",""); sig=request.args.get("sig","")
    if request.args.get("test")=="1": return "OK",200
    if not all((uid,amount,tx,sig)): return "missing parameters",400
    try: int(uid); float(amount)
    except: return "invalid parameters",400
    if not hmac.compare_digest(sign(uid,tx,amount),sig): return "invalid signature",403
    c=conn()
    if c.execute("SELECT 1 FROM transactions WHERE tx_id=?",(tx,)).fetchone():
        c.close(); return "OK",200
    c.execute("INSERT INTO transactions(tx_id,user_id,amount,status) VALUES(?,?,?,?)",(tx,int(uid),float(amount),status))
    c.execute("INSERT OR IGNORE INTO users(user_id,balance) VALUES(?,0)",(int(uid),))
    c.execute("UPDATE users SET balance=balance+? WHERE user_id=?",(float(amount),int(uid)))
    c.commit(); c.close()
    return "OK",200

async def start(update:Update,context:ContextTypes.DEFAULT_TYPE):
    u=update.effective_user; user(u.id,u.username or "")
    kb=[["🎬 المهام","💰 رصيدي"],["👥 دعوة الأصدقاء","💸 السحب"],["🏆 المتصدرون","📞 الدعم"]]
    await update.message.reply_text("أهلاً بك في شاهد واربح 💰\nاختر من القائمة:",reply_markup=ReplyKeyboardMarkup(kb,resize_keyboard=True))

async def router(update:Update,context:ContextTypes.DEFAULT_TYPE):
    u=update.effective_user; user(u.id,u.username or ""); t=update.message.text
    if t=="🎬 المهام":
        if not (OW_PUBLIC and OW_SECRET): await update.message.reply_text("⚠️ المهام قيد الإعداد حالياً."); return
        await update.message.reply_text("🎬 اختر مهمة وأكملها، وبعد التأكيد يُضاف الرصيد تلقائياً.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎯 المهام والعروض",url=wall(u.id))]]))
    elif t=="💰 رصيدي": await update.message.reply_text(f"💰 رصيدك: {balance(u.id):g} نقطة")
    elif t=="👥 دعوة الأصدقاء": await update.message.reply_text(f"👥 رابط دعوتك:\nhttps://t.me/WatchEarnArabicBot?start={u.id}")
    elif t=="💸 السحب": await update.message.reply_text("💸 السحب عبر Sham Cash.\nأرسل طلبك للدعم.")
    elif t=="🏆 المتصدرون":
        c=conn(); rows=c.execute("SELECT username,balance FROM users ORDER BY balance DESC LIMIT 10").fetchall(); c.close()
        s="🏆 المتصدرون:\n"+"".join(f"{i}. @{r['username'] or 'مستخدم'} — {float(r['balance']):g}\n" for i,r in enumerate(rows,1))
        await update.message.reply_text(s)
    elif t=="📞 الدعم": await update.message.reply_text("📞 للدعم: تواصل مع الإدارة.")

init(); bot_app=Application.builder().token(BOT_TOKEN).build()
bot_app.add_handler(CommandHandler("start",start))
bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,router))

def http():
    app.run(host="0.0.0.0",port=int(os.getenv("PORT","10000")),use_reloader=False)

if __name__=="__main__":
    threading.Thread(target=http,daemon=True).start()
    bot_app.run_polling(drop_pending_updates=True)
