import os
import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

import psycopg
from psycopg.rows import dict_row
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

TOKEN = os.environ["BOT_TOKEN"]
ADMIN_ID = int(os.getenv("ADMIN_ID", "8245481401"))
DATABASE_URL = os.environ["DATABASE_URL"]
PORT = int(os.getenv("PORT", "10000"))
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "aman-auction-webhook-2026")
DAYS = 15
BID_PRICE_CENTS = 5000
MIN_BID_CENTS = 100
MAX_BID_CENTS = 999999

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("amanchereta")


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
            name TEXT NOT NULL,
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
                (now().isoformat(),),
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
        return "ጨረታው ተዘግቷል"
    d, rem = divmod(seconds, 86400)
    h, rem = divmod(rem, 3600)
    m, _ = divmod(rem, 60)
    return f"{d} ቀን {h} ሰዓት {m} ደቂቃ"


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
    except (InvalidOperation, ValueError):
        return None
    if MIN_BID_CENTS <= cents <= MAX_BID_CENTS:
        return cents
    return None


def available(uid):
    with db() as c:
        return c.execute("""
        SELECT COUNT(*) AS n FROM opportunities
        WHERE user_id=%s AND status='available'
        """, (uid,)).fetchone()["n"]


def info():
    return f"""🎉 <b>AMANCHERETA AUCTION</b> 🎉

📱 ሽልማት፦ <b>SAMSUNG A16 (128GB / 6GB RAM)</b>

💰 አንድ Bid Opportunity፦ <b>50 ETB</b>
🔢 Bid፦ <b>1.00 – 9,999.99 ETB</b>
📌 ዝቅተኛ ጭማሪ፦ <b>0.01 ETB</b>
⏳ የጨረታ ጊዜ፦ <b>15 ቀን</b>

🎯 <b>አሰራር</b>
1️⃣ 50 ETB ይክፈሉ።
2️⃣ Receipt/Screenshot ይላኩ።
3️⃣ Admin ካረጋገጠ 1 Bid Opportunity ያገኛሉ።
4️⃣ Bid ያስገቡ።

🏆 አሸናፊው ጨረታው ከተዘጋ በኋላ ትንሹ አንድ ጊዜ ብቻ የተገባ Bid ነው።

⚠️ Duplicate Bid በመግቢያ ጊዜ አይከለከልም።
Unique/Duplicate የሚወሰነው መጨረሻ ላይ ብቻ ነው።

⏱ ቀሪ ጊዜ፦ <b>{left()}</b>"""


BANK_INFO = """💳 <b>የክፍያ መረጃ</b>

💰 50 ETB = 1 Bid Opportunity

📱 Telebirr፦ <code>0951130842</code>
🏦 CBE፦ <code>1000327168936</code>
🏦 Abyssinia፦ <code>35438297</code>
🏦 Awash፦ <code>013201291841600</code>

👤 የሂሳብ ባለቤት፦
<b>አማኑኤል ኪዱ ገብረስላሰ</b>

📸 ክፍያ ካደረጉ በኋላ Receipt/Screenshot እዚህ ይላኩ።"""


RULES_EXAMPLE = """📖 <b>የጨረታ አሰራር / ምሳሌ</b>

1️⃣ <b>50 ETB = 1 Bid Opportunity</b>

2️⃣ ዋጋው ከ <b>1.00</b> ጀምሮ በ <b>0.01</b> ይጨምራል፦

<b>1.00 → 1.01 → 1.02 → 1.03 → 1.04 → 1.05 → ... → 9,999.99</b>

3️⃣ ምሳሌ፦
👤 A → <b>1.00</b>
👤 B → <b>1.00</b>
👤 C → <b>1.01</b>
👤 D → <b>1.02</b>

🔴 1.00 ሁለት ጊዜ ስለገባ Duplicate ነው።
🟢 1.01 እና 1.02 Unique ናቸው።

🏆 ስለዚህ 1.01 ከUnique ዋጋዎች ውስጥ ዝቅተኛው ከሆነ 1.01 አሸናፊ ነው።

⚠️ የመጨረሻው ውጤት 15 ቀን ሲጠናቀቅ ብቻ ይወሰናል።"""


def menu():
    return ReplyKeyboardMarkup(
        [
            ["🎯 Bid አስገባ", "💳 ክፍያ"],
            ["📊 የእኔ ሁኔታ", "🏆 ውጤት"],
            ["📖 የጨረታ አሰራር / ምሳሌ", "ℹ️ ስለ ጨረታው"],
        ],
        resize_keyboard=True,
    )


def admin_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 አጠቃላይ", callback_data="overview"),
            InlineKeyboardButton("🧾 ክፍያዎች", callback_data="payments"),
        ],
        [
            InlineKeyboardButton("👥 ተጠቃሚዎች", callback_data="users"),
            InlineKeyboardButton("🔢 Bids", callback_data="bids"),
        ],
        [
            InlineKeyboardButton("🏆 ውጤት", callback_data="result"),
            InlineKeyboardButton("⏳ ቆጣሪ", callback_data="countdown"),
        ],
    ])


async def start(update, context):
    save_user(update.effective_user)
    await update.message.reply_text(
        "👋 <b>እንኳን ወደ AMANCHERETA AUCTION በደህና መጡ!</b>\n\n" + info(),
        parse_mode="HTML",
        reply_markup=menu(),
    )


async def bid(update, context):
    save_user(update.effective_user)
    if closed():
        return await update.message.reply_text("🔒 ጨረታው ተዘግቷል።")
    n = available(update.effective_user.id)
    if not n:
        return await update.message.reply_text(
            "❌ የBid Opportunity የለዎትም።\n💳 50 ETB ይክፈሉና Receipt ይላኩ።"
        )
    context.user_data["bid"] = True
    await update.message.reply_text(
        f"🎯 <b>Bid ያስገቡ</b>\n\n🎟️ Opportunity፦ <b>{n}</b>\n"
        "💰 1.00 – 9,999.99 ETB\n\nምሳሌ፦ <code>27.50</code>",
        parse_mode="HTML",
    )


async def status(update, context):
    uid = update.effective_user.id
    with db() as c:
        b = c.execute("SELECT COUNT(*) AS n FROM bids WHERE user_id=%s", (uid,)).fetchone()["n"]
        p = c.execute(
            "SELECT COUNT(*) AS n FROM payments WHERE user_id=%s AND status='approved'", (uid,)
        ).fetchone()["n"]
        q = c.execute(
            "SELECT COUNT(*) AS n FROM payments WHERE user_id=%s AND status='pending'", (uid,)
        ).fetchone()["n"]
    await update.message.reply_text(
        f"📊 <b>የእኔ ሁኔታ</b>\n\n"
        f"✅ የተፈቀዱ ክፍያዎች፦ {p}\n🧾 በጥበቃ ላይ፦ {q}\n"
        f"🎟️ Opportunities፦ {available(uid)}\n🔢 Bids፦ {b}\n⏳ ቀሪ፦ {left()}",
        parse_mode="HTML",
    )


def winner():
    with db() as c:
        rows = c.execute("SELECT id,user_id,amount_cents FROM bids").fetchall()
    if not rows:
        return None, 0
    counts = Counter(r["amount_cents"] for r in rows)
    unique = [a for a, n in counts.items() if n == 1]
    if not unique:
        return None, len(rows)
    amount = min(unique)
    row = next(r for r in rows if r["amount_cents"] == amount)
    return row, len(rows)


async def result(update, context):
    if not closed():
        return await update.message.reply_text(
            f"🏆 <b>ውጤት</b>\n\n🔒 ጨረታው ገና አልተዘጋም።\n⏳ ቀሪ፦ {left()}",
            parse_mode="HTML",
        )
    row, total = winner()
    if not row:
        return await update.message.reply_text(
            f"🏆 <b>የመጨረሻ ውጤት</b>\n\n❌ Unique Bid የለም።\n🔢 ጠቅላላ Bids፦ {total}",
            parse_mode="HTML",
        )
    with db() as c:
        u = c.execute("SELECT username,name FROM users WHERE id=%s", (row["user_id"],)).fetchone()
    name = "@" + u["username"] if u and u["username"] else (u["name"] if u else str(row["user_id"]))
    await update.message.reply_text(
        f"🏆 <b>የመጨረሻ ውጤት</b>\n\n"
        f"🥇 አሸናፊ፦ <b>{name}</b>\n"
        f"💰 Lowest Unique Bid፦ <b>{money(row['amount_cents'])} ETB</b>\n"
        f"🔢 ጠቅላላ Bids፦ <b>{total}</b>",
        parse_mode="HTML",
    )


async def photo(update, context):
    save_user(update.effective_user)
    fid = update.message.photo[-1].file_id
    with db() as c:
        row = c.execute(
            """INSERT INTO payments(user_id,username,name,file_id,status,created_at)
               VALUES(%s,%s,%s,%s,'pending',%s) RETURNING id""",
            (update.effective_user.id, update.effective_user.username or "",
             update.effective_user.full_name, fid, now()),
        ).fetchone()
        pid = row["id"]

    await update.message.reply_text(
        f"🧾 <b>Receipt ደርሶናል!</b>\n\n🔖 ቁጥር፦ <code>#{pid}</code>\n⏳ Admin እስኪያረጋግጥ ይጠብቁ።",
        parse_mode="HTML",
    )

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ አጽድቅ", callback_data=f"ok:{pid}"),
        InlineKeyboardButton("❌ ውድቅ", callback_data=f"no:{pid}"),
    ]])
    await context.bot.send_photo(
        ADMIN_ID, fid,
        caption=f"🧾 <b>አዲስ Receipt</b>\n\n🔖 #{pid}\n👤 {update.effective_user.full_name}\n"
                f"🆔 {update.effective_user.id}\n💰 50.00 ETB",
        parse_mode="HTML",
        reply_markup=kb,
    )


async def text(update, context):
    t = update.message.text
    if t == "🎯 Bid አስገባ":
        return await bid(update, context)
    if t == "💳 ክፍያ":
        return await update.message.reply_text(BANK_INFO, parse_mode="HTML")
    if t == "📊 የእኔ ሁኔታ":
        return await status(update, context)
    if t == "🏆 ውጤት":
        return await result(update, context)
    if t == "📖 የጨረታ አሰራር / ምሳሌ":
        return await update.message.reply_text(RULES_EXAMPLE, parse_mode="HTML")
    if t == "ℹ️ ስለ ጨረታው":
        return await update.message.reply_text(info(), parse_mode="HTML")

    if update.effective_user.id == ADMIN_ID and context.user_data.get("broadcast"):
        context.user_data["broadcast"] = False
        with db() as c:
            ids = [r["id"] for r in c.execute("SELECT id FROM users").fetchall()]
        sent = failed = 0
        for uid in ids:
            try:
                await context.bot.send_message(uid, update.message.text)
                sent += 1
            except Exception:
                failed += 1
        return await update.message.reply_text(f"📢 ማስታወቂያ ተልኳል!\n\n✅ {sent}\n❌ {failed}")

    if context.user_data.get("bid"):
        amount = parse_bid(t)
        if amount is None:
            return await update.message.reply_text("❌ 1.00–9,999.99 ETB በ2 decimal ያስገቡ።")

        with db() as c:
            opp = c.execute(
                """SELECT id FROM opportunities
                   WHERE user_id=%s AND status='available'
                   ORDER BY id LIMIT 1 FOR UPDATE""",
                (update.effective_user.id,),
            ).fetchone()
            if not opp:
                return await update.message.reply_text("❌ Opportunity የለም።")
            c.execute(
                "UPDATE opportunities SET status='used',used_at=%s WHERE id=%s",
                (now(), opp["id"]),
            )
            row = c.execute(
                """INSERT INTO bids(user_id,amount_cents,opportunity_id,created_at)
                   VALUES(%s,%s,%s,%s) RETURNING id""",
                (update.effective_user.id, amount, opp["id"], now()),
            ).fetchone()
            bid_id = row["id"]

        context.user_data["bid"] = False
        await update.message.reply_text(
            f"✅ <b>Bid ተሳክቷል!</b>\n\n💰 {money(amount)} ETB\n"
            f"🔖 Bid #{bid_id}\n🎟️ ቀሪ Opportunity፦ {available(update.effective_user.id)}",
            parse_mode="HTML",
        )


async def admin(update, context):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("⛔ Admin ብቻ ነው።")
    await update.message.reply_text(
        f"👨‍💼 <b>Admin Dashboard</b>\n\n"
        f"{'🔴 ተዘግቷል' if closed() else '🟢 እየሰራ ነው'}\n⏳ {left()}",
        parse_mode="HTML",
        reply_markup=admin_menu(),
    )


async def cb(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        return await q.answer("⛔ Admin ብቻ ነው።", show_alert=True)
    await q.answer()
    d = q.data

    if d.startswith(("ok:", "no:")):
        pid = int(d.split(":")[1])
        approve = d.startswith("ok:")
        with db() as c:
            p = c.execute("SELECT * FROM payments WHERE id=%s FOR UPDATE", (pid,)).fetchone()
            if not p or p["status"] != "pending":
                return await q.answer("ይህ ክፍያ ከዚህ በፊት ተመርምሯል።", show_alert=True)
            status_value = "approved" if approve else "rejected"
            c.execute(
                "UPDATE payments SET status=%s,reviewed_at=%s WHERE id=%s",
                (status_value, now(), pid),
            )
            if approve:
                c.execute(
                    """INSERT INTO opportunities(user_id,payment_id,status,created_at)
                       VALUES(%s,%s,'available',%s)
                       ON CONFLICT DO NOTHING""",
                    (p["user_id"], pid, now()),
                )
        await context.bot.send_message(
            p["user_id"],
            "✅ ክፍያዎ ተፈቅዷል! 🎟️ 1 Bid Opportunity አግኝተዋል። /bid ይጠቀሙ።"
            if approve else
            "❌ ክፍያዎ አልተፈቀደም። Receipt እንደገና ይላኩ።",
        )
        try:
            await q.edit_message_caption(
                (q.message.caption or "") + ("\n\n✅ ተፈቅዷል" if approve else "\n\n❌ ውድቅ ተደርጓል"),
                parse_mode="HTML",
                reply_markup=None,
            )
        except Exception:
            pass
        return

    if d == "overview":
        with db() as c:
            u = c.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
            p = c.execute("SELECT COUNT(*) AS n FROM payments").fetchone()["n"]
            ap = c.execute("SELECT COUNT(*) AS n FROM payments WHERE status='approved'").fetchone()["n"]
            pd = c.execute("SELECT COUNT(*) AS n FROM payments WHERE status='pending'").fetchone()["n"]
            b = c.execute("SELECT COUNT(*) AS n FROM bids").fetchone()["n"]
        return await q.message.reply_text(
            f"📊 <b>Dashboard</b>\n\n👥 Users፦ {u}\n💰 Approved payments፦ {ap}\n"
            f"🧾 Payments፦ {p}\n⏳ Pending፦ {pd}\n🔢 Bids፦ {b}\n⏱ ቀሪ፦ {left()}",
            parse_mode="HTML",
        )

    if d == "result":
        row, total = winner()
        if not closed():
            msg = f"🏆 <b>ውጤት</b>\n\n🔒 ገና አልተዘጋም። ⏳ {left()}"
        elif not row:
            msg = f"🏆 <b>ውጤት</b>\n\n❌ Unique Bid የለም።\n🔢 Total Bids፦ {total}"
        else:
            with db() as c:
                u = c.execute("SELECT username,name FROM users WHERE id=%s", (row["user_id"],)).fetchone()
            name = "@" + u["username"] if u and u["username"] else (u["name"] if u else str(row["user_id"]))
            msg = f"🏆 <b>አሸናፊ</b>\n\n👤 {name}\n💰 {money(row['amount_cents'])} ETB\n🔢 Total Bids፦ {total}"
        return await q.message.reply_text(msg, parse_mode="HTML")

    if d == "countdown":
        return await q.message.reply_text(f"⏳ <b>ቆጣሪ</b>\n\n{left()}", parse_mode="HTML")

    if d in ("users", "bids", "payments"):
        with db() as c:
            if d == "users":
                rows = c.execute("SELECT id,name,username FROM users ORDER BY id DESC LIMIT 30").fetchall()
                msg = "👥 <b>ተጠቃሚዎች</b>\n\n" + "\n".join(
                    f"• {r['name']} @{r['username'] or ''} — {r['id']}" for r in rows
                )
            elif d == "bids":
                rows = c.execute(
                    "SELECT id,user_id,amount_cents FROM bids ORDER BY id DESC LIMIT 30"
                ).fetchall()
                msg = "🔢 <b>Recent Bids</b>\n\n" + "\n".join(
                    f"#{r['id']} — {money(r['amount_cents'])} ETB — ID {r['user_id']}" for r in rows
                )
            else:
                rows = c.execute(
                    "SELECT id,name,status FROM payments ORDER BY id DESC LIMIT 20"
                ).fetchall()
                msg = "🧾 <b>Payments</b>\n\n" + "\n".join(
                    f"#{r['id']} — {r['status']} — {r['name']}" for r in rows
                )
        return await q.message.reply_text(msg or "ምንም መረጃ የለም።", parse_mode="HTML")


async def health(update, context):
    return


def main():
    init_db()
    app = Application.builder().token(TOKEN).build()

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
