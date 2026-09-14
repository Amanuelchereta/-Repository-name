import os
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import psycopg
from psycopg.rows import dict_row
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# ሎግንግ ማስተካከል
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
log = logging.getLogger(__name__)

# ከ Environment Variables የሚወሰዱ መረጃዎች
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "8245481401"))
DATABASE_URL = os.getenv("DATABASE_URL")
PORT = int(os.getenv("PORT", "10000"))
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "amanauction2026")

DAYS = 15
BID_PRICE_CENTS = 5000
MIN_BID_CENTS = 100
MAX_BID_CENTS = 999999

# ዳታቤዝ እና የሰዓት ማስተካከያ
def db():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)

def now():
    return datetime.now(timezone.utc)

def money(cents):
    return f"{cents / 100:.2f}"

def init_db():
    with db() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS users (
                id BIGINT PRIMARY KEY,
                username TEXT,
                name TEXT NOT NULL,
                phone TEXT,
                created_at TIMESTAMPTZ NOT NULL
            );
            CREATE TABLE IF NOT EXISTS payments (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES users(id),
                username TEXT,
                name TEXT,
                file_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TIMESTAMPTZ NOT NULL,
                reviewed_at TIMESTAMPTZ
            );
            CREATE TABLE IF NOT EXISTS opportunities (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES users(id),
                payment_id BIGINT NOT NULL REFERENCES payments(id),
                status TEXT NOT NULL DEFAULT 'available',
                created_at TIMESTAMPTZ NOT NULL,
                used_at TIMESTAMPTZ
            );
            CREATE TABLE IF NOT EXISTS bids (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES users(id),
                amount_cents INTEGER NOT NULL,
                opportunity_id BIGINT NOT NULL UNIQUE REFERENCES opportunities(id),
                created_at TIMESTAMPTZ NOT NULL
            );
        """)
        row = c.execute("SELECT value FROM settings WHERE key='start'").fetchone()
        if not row:
            c.execute(
                "INSERT INTO settings(key,value) VALUES('start',%s)",
                (now().isoformat(),)
            )

def start_time():
    with db() as c:
        row = c.execute("SELECT value FROM settings WHERE key='start'").fetchone()
        return datetime.fromisoformat(row["value"])

def end_time():
    return start_time() + timedelta(days=DAYS)

def closed():
    return now() >= end_time()

def left():
    seconds = int((end_time() - now()).total_seconds())
    if seconds <= 0:
        return "ጨረታው ተጠናቀዋል"
    d, rem = divmod(seconds, 86400)
    h, rem = divmod(rem, 3600)
    m, _ = divmod(rem, 60)
    return f"{d} ቀን፣ {h} ሰዓት፣ {m} ደቂቃ"

def save_user(u, phone=None):
    with db() as c:
        c.execute("""
            INSERT INTO users(id,username,name,phone,created_at)
            VALUES(%s,%s,%s,%s,%s)
            ON CONFLICT(id) DO UPDATE SET
                username=EXCLUDED.username,
                name=EXCLUDED.name,
                phone=COALESCE(EXCLUDED.phone, users.phone)
        """, (u.id, u.username, u.full_name, phone, now()))

def parse_bid(text):
    try:
        d = Decimal(text.strip().replace(",", ""))
        if d.as_tuple().exponent < -2:
            return None
        cents = int(d * 100)
        if MIN_BID_CENTS <= cents <= MAX_BID_CENTS:
            return cents
    except InvalidOperation:
        pass
    return None

def available(uid):
    with db() as c:
        return c.execute(
            "SELECT COUNT(*) AS n FROM opportunities WHERE user_id=%s AND status='available'",
            (uid,)
        ).fetchone()["n"]

def info():
    return f"""<b>🔥 AMANCHERETA AUCTION 🔥</b>

📱 ዕቃ:- <b>SAMSUNG A16 (128GB / 6GB RAM)</b>

💰 1 Bid Opportunity:- <b>50 ETB</b>
💵 Bid:- <b>1.00 - 9,999.99 ETB</b>
📌 ዝቅተኛ ጭማሪ:- <b>0.01 ETB</b>
⏳ የጨረታ ጊዜ:- <b>15 ቀን</b>

🎯 <b>አሰራር</b>
1️⃣ 50 ETB ይክፈሉ
2️⃣ Receipt/Screenshot ይላኩ
3️⃣ Admin ሲያረጋግጥ 1 Bid Opportunity ያገኛሉ
4️⃣ Bid ያስገቡ

🏆 አሸናፊው ጨረታው ከተዘጋ በኋላ ትክክለኛ አንድ ጊዜ ብቻ የተገባ Bid ነው።
⚠️ Duplicate Bid በመሆኑ ጊዜ አይከለከልም
- Unique/Duplicate የሚወሰነው መጠን ላይ ብቻ ነው።

⏳ ቀርቷል:- <b>{left()}</b>

BANK INFO: 💳 <b>የክፍያ መረጃዎች</b>

💰 50 ETB = 1 Bid Opportunity

📱 Telebirr:- <code>0951130842</code>
🏦 CBE:- <code>1000327168936</code>
🏦 Abyssinia:- <code>35438297</code>
🏦 Awash:- <code>013201291841600</code>

👤 የアカウント ኃላፊነት:-
<b>>አማኑኤል ኪ.አ ኃ/የተ/የግ/ማ</b>

📸 ከፍ ከፍ በኋላ Receipt/Screenshot አሁኑ ይላኩ።"""

def menu():
    return ReplyKeyboardMarkup([
        ["🎯 Bid አስገባ", "💳 ከፍያ"],
        ["📊 የኔ ሁኔታ", "🏆 ውጤት"],
        ["ℹ️ መረጃዎች/ አሰራር", "📞 ስለ ጨረታው"]
    ], resize_keyboard=True)

def admin_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💳 ክፍያዎች", callback_data="payments"),
            InlineKeyboardButton("👥 ተጠቃሚዎች", callback_data="users"),
        ],
        [
            InlineKeyboardButton("📊 Bids", callback_data="bids"),
            InlineKeyboardButton("🏆 ውጤት", callback_data="result"),
        ],
        [
            InlineKeyboardButton("⏳ ቆጣሪ", callback_data="countdown")
        ]
    ])

# ቦት ትዕዛዞች
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    save_user(update.effective_user)
    await update.message.reply_text(
        f"ሰላም! <b>{update.effective_user.first_name}</b> ወደ አማር ጨረታ እንኳን ደህና መጡ!\n\n{info()}",
        parse_mode="HTML",
        reply_markup=menu()
    )

async def bid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    save_user(update.effective_user)
    if closed():
        return await update.message.reply_text("🔒 ጨረታው ተዘግቷል")
    n = available(update.effective_user.id)
    if not n:
        return await update.message.reply_text(
            "❌ <b>Bid Opportunity የለዎትም!</b>\n💳 50 ETB ከፍለው Receipt ይላኩ።",
            parse_mode="HTML"
        )
    context.user_data["bid"] = True
    await update.message.reply_text(
        f"🎯 <b>Bid ለማስገባት</b>\n\nOpportunity: <b>{n}</b>\n💰 1.00 - 9,999.99 ETB\nምሳሌ:- <code>27.50</code>",
        parse_mode="HTML"
    )

async def result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not closed():
        return await update.message.reply_text(
            f"🏆 <b>የጨረታ ውጤት</b>\n\nጨረታው ገና አልተጠናቀቀም!\n⏳ ቀርቷል:- <b>{left()}</b>",
            parse_mode="HTML"
        )
    await update.message.reply_text("የጨረታው ጊዜ አልቋል፣ ውጤት እየተሰላ ነው።")

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text("🛠 <b>ወደ አድሚን ፓነል እንኳን ደህና መጡ</b>", parse_mode="HTML", reply_markup=admin_menu())

async def cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID:
        return
    data = q.data
    if data.startswith("ok_"):
        pid = int(data.split("_")[1])
        with db() as c:
            p = c.execute("SELECT * FROM payments WHERE id=%s", (pid,)).fetchone()
            if p and p["status"] == "pending":
                c.execute("UPDATE payments SET status='approved', reviewed_at=%s WHERE id=%s", (now(), pid))
                c.execute("INSERT INTO opportunities(user_id,payment_id,created_at) VALUES(%s,%s,%s)", (p["user_id"], pid, now()))
        await q.edit_message_caption("✅ <b>ክፍያው ጸድቋል!</b>", parse_mode="HTML")
        try:
            await context.bot.send_message(p["user_id"], "🎉 ክፍያዎ ጸድቋል! አሁን Bid ማድረግ ይችላሉ።")
        except:
            pass
    elif data.startswith("no_"):
        pid = int(data.split("_")[1])
        with db() as c:
            p = c.execute("SELECT * FROM payments WHERE id=%s", (pid,)).fetchone()
            if p and p["status"] == "pending":
                c.execute("UPDATE payments SET status='rejected', reviewed_at=%s WHERE id=%s", (now(), pid))
        await q.edit_message_caption("❌ <b>ክፍያው ውድቅ ተደርጓል</b>", parse_mode="HTML")
        try:
            await context.bot.send_message(p["user_id"], "❌ ክፍያዎ ውድቅ ተደርጓል። እባክዎ በትክክል እንደገና ይሞክሩ።")
        except:
            pass

async def photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    save_user(update.effective_user)
    if closed():
        return await update.message.reply_text("🔒 ጨረታው ተዘግቷል")
    p = update.message.photo[-1]
    fid = p.file_id
    with db() as c:
        row = c.execute("""
            INSERT INTO payments(user_id,username,name,file_id,status,created_at)
            VALUES(%s,%s,%s,%s,'pending',%s) RETURNING id
        """, (
            update.effective_user.id,
            update.effective_user.username or "",
            update.effective_user.full_name,
            fid,
            now()
        )).fetchone()
        pid = row["id"]

    await update.message.reply_text(
        f"📸 <b>Receipt ተቀብለናል!</b>\n🆔 ቁጥር:- <code>#{pid}</code>\n⏳ Admin እንዲያረጋግጥልን ይጠብቁ።",
        parse_mode="HTML"
    )
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ አዎ", callback_data=f"ok_{pid}"),
            InlineKeyboardButton("❌ ውድቅ", callback_data=f"no_{pid}"),
        ]
    ])
    await context.bot.send_photo(
        ADMIN_ID,
        fid,
        caption=f"🔔 <b>አዲስ Receipt</b>\n🆔 #{pid}\n👤 @{update.effective_user.username}\n🆔 <code>{update.effective_user.id}</code>\n💰 50.00 ETB",
        parse_mode="HTML",
        reply_markup=kb
    )

async def text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = update.message.text
    if t == "ℹ️ መረጃዎች/ አሰራር":
        await update.message.reply_text(info(), parse_mode="HTML")
    elif t == "📞 ስለ ጨረታው":
        await update.message.reply_text("ለማንኛውም ጥያቄ ከአስተዳዳሪው ጋር ይነጋገሩ።")
    elif t == "📊 የኔ ሁኔታ":
        uid = update.effective_user.id
        with db() as c:
            bids_cnt = c.execute("SELECT COUNT(*) AS n FROM bids WHERE user_id=%s", (uid,)).fetchone()["n"]
            app_cnt = c.execute("SELECT COUNT(*) AS n FROM payments WHERE user_id=%s AND status='approved'", (uid,)).fetchone()["n"]
        await update.message.reply_text(
            f"📊 <b>የእርስዎ ሁኔታ</b>\n\n✅ የጸደቁ ክፍያዎች:- {app_cnt}\n🎯 Opportunities:- {available(uid)}\n📌 Bids የተደረጉ:- {bids_cnt}\n⏳ ቀርቷል:- {left()}",
            parse_mode="HTML"
        )
    elif context.user_data.get("bid"):
        context.user_data["bid"] = False
        cents = parse_bid(t)
        if not cents:
            return await update.message.reply_text("❌ ትክክለኛ የዋጋ መጠን ያስገቡ (ምሳሌ:- 27.50)")
        uid = update.effective_user.id
        with db() as c:
            op = c.execute(
                "SELECT id FROM opportunities WHERE user_id=%s AND status='available' LIMIT 1",
                (uid,)
            ).fetchone()
            if not op:
                return await update.message.reply_text("❌ የሚጠቀምበት Opportunity የለዎትም!")
            try:
                c.execute(
                    "INSERT INTO bids(user_id,amount_cents,opportunity_id,created_at) VALUES(%s,%s,%s,%s)",
                    (uid, cents, op["id"], now())
                )
                c.execute("UPDATE opportunities SET status='used', used_at=%s WHERE id=%s", (now(), op["id"]))
                await update.message.reply_text(f"✅ <b>Bid ተመዝግቧል!</b> ዋጋ፦ {money(cents)} ETB", parse_mode="HTML")
            except Exception as e:
                log.error(e)
                await update.message.reply_text("❌ ስህተት አጋጥሟል ወይም ይህ Opportunity ተይዟል።")

def main():
    if not BOT_TOKEN:
        log.error("BOT_TOKEN environment variable is missing!")
        return

    init_db()

    # የቴሌግራም አፕሊኬሽን መገንባት
    app = Application.builder().token(BOT_TOKEN).build()

    # ሃንድለሮችን ማስገባት
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("bid", bid))
    app.add_handler(CommandHandler("result", result))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CallbackQueryHandler(cb))
    app.add_handler(MessageHandler(filters.PHOTO, photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text))

    if not RENDER_EXTERNAL_URL:
        raise RuntimeError("RENDER_EXTERNAL_URL አልተገኘም። Render Web Service ላይ ብቻ አስኪዱ።")

    webhook_url = f"{RENDER_EXTERNAL_URL}/{WEBHOOK_SECRET}"
    log.info("Starting webhook: %s", webhook_url)

    # ዌብሁክን በፖርት 10000 ማስኬድ (Render በቀጥታ ዌብሁክ ዩአርኤሉን ይጠቀማል)
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=WEBHOOK_SECRET,
        webhook_url=webhook_url,
        secret_token=WEBHOOK_SECRET,
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )

if __name__ == "__main__":
    main()
