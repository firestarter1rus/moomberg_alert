import logging
import os
from datetime import datetime

from flask import Flask, request, jsonify
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
import asyncio

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)

# Global variables
BOT_TOKEN = None
CHAT_ID = None
WEBHOOK_URL = None
telegram_app = None
scheduler = None

def init_config():
    """Initialize configuration."""
    global BOT_TOKEN, CHAT_ID, WEBHOOK_URL
    
    BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id_str = os.getenv("TELEGRAM_CHAT_ID")
    render_url = os.getenv("RENDER_EXTERNAL_URL")  # Render sets this automatically
    
    if not BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN is required")
    
    if not chat_id_str:
        raise ValueError("TELEGRAM_CHAT_ID is required")
    
    try:
        CHAT_ID = int(chat_id_str)
        logger.info(f"✅ Chat ID configured: {CHAT_ID}")
    except ValueError:
        raise ValueError(f"TELEGRAM_CHAT_ID must be integer, got: {chat_id_str}")
    
    # Set webhook URL
    if render_url:
        WEBHOOK_URL = f"{render_url}/webhook"
        logger.info(f"✅ Webhook URL: {WEBHOOK_URL}")
    else:
        logger.warning("⚠️ RENDER_EXTERNAL_URL not set, webhook may not work")

async def send_telegram_message(text: str):
    """Send message to configured chat."""
    try:
        bot = Bot(token=BOT_TOKEN)
        await bot.send_message(chat_id=CHAT_ID, text=text, parse_mode='Markdown')
        logger.info(f"✅ Message sent: {text[:50]}...")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to send message: {e}")
        return False

def hourly_task():
    """Task that runs every hour."""
    logger.info("⏰ Running hourly task...")
    
    now = datetime.now()
    time_str = now.strftime("%H:%M %d.%m.%Y")
    message = f"💓 *Hourly Update*\n⏰ {time_str}\n\n✅ System is running"
    
    # Run async function
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(send_telegram_message(message))
    finally:
        loop.close()

def startup_task():
    """Task that runs on startup."""
    logger.info("🚀 Running startup task...")
    
    now = datetime.now()
    time_str = now.strftime("%H:%M %d.%m.%Y")
    message = f"🤖 *Bot Started*\n⏰ {time_str}\n\n✅ Webhook mode active"
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(send_telegram_message(message))
    finally:
        loop.close()

# Telegram command handlers
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /start command."""
    user = update.effective_user
    await update.message.reply_text(
        f"👋 Hello {user.first_name}!\n\n"
        f"🤖 Bot is running in webhook mode.\n"
        f"💬 Your Chat ID: `{update.effective_chat.id}`\n\n"
        f"Use /help for available commands.",
        parse_mode='Markdown'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /help command."""
    await update.message.reply_text(
        "📋 *Available Commands:*\n\n"
        "/start - Start the bot\n"
        "/help - Show this message\n"
        "/status - Check bot status\n"
        "/test - Send test message\n"
        "/id - Get your chat ID",
        parse_mode='Markdown'
    )

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /status command."""
    now = datetime.now()
    await update.message.reply_text(
        f"✅ *Bot Status*\n\n"
        f"⏰ Time: {now.strftime('%H:%M %d.%m.%Y')}\n"
        f"📡 Mode: Webhook\n"
        f"🔄 Scheduler: Active\n"
        f"💬 Configured Chat: `{CHAT_ID}`",
        parse_mode='Markdown'
    )

async def test_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /test command."""
    await update.message.reply_text("🧪 Sending test message to configured chat...")
    
    now = datetime.now()
    message = f"🧪 *Test Message*\n⏰ {now.strftime('%H:%M %d.%m.%Y')}"
    
    success = await send_telegram_message(message)
    
    if success:
        await update.message.reply_text("✅ Test message sent!")
    else:
        await update.message.reply_text("❌ Failed to send test message. Check logs.")

async def id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /id command."""
    chat = update.effective_chat
    await update.message.reply_text(
        f"📱 *Chat Information:*\n\n"
        f"🆔 Chat ID: `{chat.id}`\n"
        f"📋 Type: {chat.type}\n"
        f"👤 Title: {chat.title if chat.title else 'N/A'}",
        parse_mode='Markdown'
    )

# Flask routes
@app.route('/')
def home():
    """Health check endpoint."""
    return jsonify({
        "status": "alive",
        "service": "telegram-bot",
        "mode": "webhook",
        "timestamp": datetime.now().isoformat()
    })

@app.route('/health')
def health():
    """Detailed health check."""
    return jsonify({
        "status": "healthy",
        "bot": "running",
        "chat_id": CHAT_ID,
        "webhook_url": WEBHOOK_URL,
        "scheduler": "active" if scheduler and scheduler.running else "inactive"
    })

@app.route('/webhook', methods=['POST'])
def webhook():
    """Webhook endpoint for Telegram updates."""
    if request.method == "POST":
        try:
            update = Update.de_json(request.get_json(force=True), telegram_app.bot)
            
            # Process update asynchronously
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                async def process():
                    await telegram_app.process_update(update)
                
                loop.run_until_complete(process())
            finally:
                loop.close()
            
            return jsonify({"ok": True})
        except Exception as e:
            logger.error(f"❌ Webhook error: {e}", exc_info=True)
            return jsonify({"ok": False, "error": str(e)}), 500
    
    return jsonify({"ok": False, "error": "Only POST allowed"}), 405

@app.route('/trigger')
def trigger():
    """Manual trigger for hourly task."""
    try:
        hourly_task()
        return jsonify({"status": "success", "message": "Hourly task triggered"})
    except Exception as e:
        logger.error(f"Error in /trigger: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/set-webhook')
def set_webhook():
    """Manually set webhook (for debugging)."""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def setup():
            # Make sure app is initialized
            if not telegram_app._initialized:
                await telegram_app.initialize()
            
            await telegram_app.bot.set_webhook(url=WEBHOOK_URL)
            info = await telegram_app.bot.get_webhook_info()
            return info
        
        try:
            info = loop.run_until_complete(setup())
            return jsonify({
                "status": "success",
                "webhook_url": info.url,
                "pending_update_count": info.pending_update_count
            })
        finally:
            loop.close()
            
    except Exception as e:
        logger.error(f"Error setting webhook: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500

def init_telegram():
    """Initialize Telegram bot application."""
    global telegram_app
    
    logger.info("🤖 Initializing Telegram bot...")
    
    # Create application
    telegram_app = Application.builder().token(BOT_TOKEN).build()
    
    # Add command handlers
    telegram_app.add_handler(CommandHandler("start", start_command))
    telegram_app.add_handler(CommandHandler("help", help_command))
    telegram_app.add_handler(CommandHandler("status", status_command))
    telegram_app.add_handler(CommandHandler("test", test_command))
    telegram_app.add_handler(CommandHandler("id", id_command))
    
    logger.info("✅ Command handlers registered")
    
    # Initialize and set webhook
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        async def setup_webhook():
            # Initialize the application
            await telegram_app.initialize()
            await telegram_app.bot.set_webhook(url=WEBHOOK_URL)
            info = await telegram_app.bot.get_webhook_info()
            logger.info(f"✅ Webhook set: {info.url}")
            logger.info(f"   Pending updates: {info.pending_update_count}")
        
        loop.run_until_complete(setup_webhook())
    except Exception as e:
        logger.error(f"❌ Failed to set webhook: {e}")
    finally:
        loop.close()
    
    return telegram_app

def init_scheduler():
    """Initialize task scheduler."""
    global scheduler
    
    logger.info("⏰ Initializing scheduler...")
    
    scheduler = BackgroundScheduler()
    
    # Schedule hourly task (every hour at :00)
    scheduler.add_job(
        hourly_task,
        trigger='cron',
        minute=0,
        id='hourly_task',
        name='Hourly Telegram Update',
        misfire_grace_time=300
    )
    
    scheduler.start()
    logger.info("✅ Scheduler started - hourly task at :00")
    
    return scheduler

def initialize_all():
    """Initialize all components."""
    logger.info("=" * 60)
    logger.info("🚀 TELEGRAM BOT INITIALIZATION")
    logger.info("=" * 60)
    
    # Load config
    init_config()
    
    # Initialize Telegram
    init_telegram()
    
    # Initialize scheduler
    init_scheduler()
    
    # Run startup task
    startup_task()
    
    logger.info("=" * 60)
    logger.info("✅ Bot fully initialized")
    logger.info("📡 Webhook mode active")
    logger.info("=" * 60)

def cleanup():
    """Cleanup resources on shutdown."""
    global telegram_app, scheduler
    
    logger.info("🛑 Shutting down...")
    
    if scheduler and scheduler.running:
        scheduler.shutdown()
        logger.info("✅ Scheduler stopped")
    
    if telegram_app:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            async def shutdown():
                if telegram_app._initialized:
                    await telegram_app.shutdown()
                    logger.info("✅ Telegram app shutdown")
        
            loop.run_until_complete(shutdown())
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
        finally:
            loop.close()

import atexit
atexit.register(cleanup)

# Initialize when module loads (for Gunicorn)
try:
    initialize_all()
except Exception as e:
    logger.error(f"❌ Initialization failed: {e}")
    raise

def main():
    """Main function for direct execution."""
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"🌐 Starting Flask server on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)

if __name__ == '__main__':
    main()