import os
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

# ሎግንግ ማስተካከል
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
log = logging.getLogger(__name__)

# ከ Environment Variables የሚወሰዱ መረጃዎች
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "amanauction2026")
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")
DATABASE_URL = os.getenv("DATABASE_URL")
PORT = int(os.getenv("PORT", "10000"))

# 1. ለ Render ጤና ማረጋገጫ (Health Check) የሚያገለግል ዌብ ሰርቨር
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Amanchereta Auction Bot is fully operational!")

def run_health_server():
    server_address = ('0.0.0.0', PORT)
    httpd = HTTPServer(server_address, HealthCheckHandler)
    log.info(f"Health check server running on port {PORT}")
    httpd.serve_forever()

# 2. የቦት ዋና ዋና ተግባራት (Placeholder Functions - ካሉህ በራስህ ፋይሎች መቀየር ትችላለህ)
async def start(update: Update, context):
    await update.message.reply_text("ሰላም! ወደ አማር ጨረታ (Amanchereta) እንኳን በደህና መጡ።")

async def bid(update: Update, context):
    await update.message.reply_text("የጨረታ ዋጋ ለማስገባት እባክዎ መመሪያውን ይከተሉ።")

async def result(update: Update, context):
    await update.message.reply_text("የጨረታ ውጤቶች እዚህ ይታያሉ።")

async def admin(update: Update, context):
    await update.message.reply_text("ወደ አድሚን ፓነል እንኳን በደህና መጡ።")

async def cb(update: Update, context):
    query = update.callback_query
    await query.answer()

async def photo(update: Update, context):
    await update.message.reply_text("ፎቶዎ ተቀብሏል።")

async def text(update: Update, context):
    pass

def main():
    if not BOT_TOKEN:
        log.error("BOT_TOKEN environment variable is missing!")
        return

    # የቴሌግራም አፕሊኬሽን መገንባት
    app = Application.builder().token(BOT_TOKEN).build()

    # የትዕዛዝ ማስተናገጃዎችን (Handlers) መጨመር
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("bid", bid))
    app.add_handler(CommandHandler("result", result))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CallbackQueryHandler(cb))
    app.add_handler(MessageHandler(filters.PHOTO, photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text))

    if not RENDER_EXTERNAL_URL:
        raise RuntimeError("RENDER_EXTERNAL_URL አልተገኘም። Render Web Service ላይ ብቻ አስኪዱ።")

    # ጤና ማረጋገጫ ሰርቨርን በጀርባ (Background Thread) በፖርት 10000 ማስጀመር
    threading.Thread(target=run_health_server, daemon=True).start()

    webhook_url = f"{RENDER_EXTERNAL_URL.rstrip('/')}/{WEBHOOK_SECRET}"
    log.info("Starting webhook: %s", webhook_url)

    # ዌብሁክን ማስኬድ (Render ፖርቱን ይጠቀማል)
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
