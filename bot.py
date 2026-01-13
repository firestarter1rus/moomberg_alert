import logging
import os
import asyncio
from datetime import datetime
from threading import Thread

import requests
from flask import Flask, jsonify
from apscheduler.schedulers.background import BackgroundScheduler
from telegram import Bot
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize Flask app for health checks
app = Flask(__name__)

# Global bot instance
bot = None
CHAT_ID = None

def init_bot():
    """Initialize Telegram bot."""
    global bot, CHAT_ID
    
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
    
    if not token:
        logger.error("❌ TELEGRAM_BOT_TOKEN not set")
        raise ValueError("TELEGRAM_BOT_TOKEN is required")
    
    if not CHAT_ID:
        logger.error("❌ TELEGRAM_CHAT_ID not set")
        raise ValueError("TELEGRAM_CHAT_ID is required")
    
    bot = Bot(token=token)
    logger.info("✅ Bot initialized successfully")

async def send_message(text):
    """Send message to configured chat."""
    try:
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
    message = f"💓 Hourly Update: {time_str}"
    
    # Run async function in sync context
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(send_message(message))
        loop.close()
    except Exception as e:
        logger.error(f"❌ Error in hourly task: {e}")

def startup_task():
    """Task that runs once on startup."""
    logger.info("🚀 Running startup task...")
    
    now = datetime.now()
    time_str = now.strftime("%H:%M %d.%m.%Y")
    message = f"🤖 *Bot Started*\n⏰ {time_str}\n\n✅ System is online and monitoring"
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(send_message(message))
        loop.close()
    except Exception as e:
        logger.error(f"❌ Error in startup task: {e}")

# Flask routes for health checks
@app.route('/')
def home():
    """Root endpoint for health check."""
    return jsonify({
        "status": "alive",
        "service": "telegram-bot",
        "timestamp": datetime.now().isoformat()
    })

@app.route('/health')
def health():
    """Health check endpoint."""
    return jsonify({
        "status": "healthy",
        "bot": "running",
        "chat_id": CHAT_ID if CHAT_ID else "not_set"
    })

@app.route('/trigger')
def trigger():
    """Manual trigger endpoint for testing."""
    try:
        hourly_task()
        return jsonify({"status": "success", "message": "Task triggered manually"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

def run_flask():
    """Run Flask server."""
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"🌐 Starting Flask server on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

def main():
    """Main function."""
    logger.info("=" * 50)
    logger.info("🤖 TELEGRAM BOT STARTING")
    logger.info("=" * 50)
    
    # Initialize bot
    try:
        init_bot()
    except Exception as e:
        logger.error(f"❌ Failed to initialize bot: {e}")
        return
    
    # Initialize scheduler
    scheduler = BackgroundScheduler()
    
    # Schedule hourly task
    # Runs every hour at minute 0 (e.g., 10:00, 11:00, 12:00, etc.)
    scheduler.add_job(
        hourly_task,
        trigger='cron',
        minute=0,
        id='hourly_task',
        name='Hourly Telegram Update'
    )
    
    # Start scheduler
    scheduler.start()
    logger.info("✅ Scheduler started - hourly task scheduled")
    
    # Run startup task
    startup_task()
    
    # Start Flask in main thread (required by Render)
    logger.info("🚀 Bot fully initialized - starting Flask server")
    run_flask()

if __name__ == '__main__':
    main()