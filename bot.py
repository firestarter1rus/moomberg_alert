import logging
import os
from datetime import datetime

import requests
from flask import Flask, jsonify
from apscheduler.schedulers.background import BackgroundScheduler
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

# Global variables
BOT_TOKEN = None
CHAT_ID = None

def init_bot():
    """Initialize bot configuration."""
    global BOT_TOKEN, CHAT_ID
    
    BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id_str = os.getenv("TELEGRAM_CHAT_ID")
    
    if not BOT_TOKEN:
        logger.error("❌ TELEGRAM_BOT_TOKEN not set")
        raise ValueError("TELEGRAM_BOT_TOKEN is required")
    
    if not chat_id_str:
        logger.error("❌ TELEGRAM_CHAT_ID not set")
        raise ValueError("TELEGRAM_CHAT_ID is required")
    
    # Convert CHAT_ID to integer (can be negative for groups)
    try:
        CHAT_ID = int(chat_id_str)
        logger.info(f"✅ Bot configuration loaded successfully (Chat ID: {CHAT_ID})")
    except ValueError:
        logger.error(f"❌ TELEGRAM_CHAT_ID must be a number, got: {chat_id_str}")
        raise ValueError("TELEGRAM_CHAT_ID must be a valid integer")

def send_message(text):
    """Send message to configured chat using requests."""
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {
            'chat_id': CHAT_ID,
            'text': text,
            'parse_mode': 'Markdown'
        }
        
        logger.info(f"Sending message to chat_id: {CHAT_ID}")
        response = requests.post(url, json=payload, timeout=10)
        
        # Log response for debugging
        if response.status_code != 200:
            logger.error(f"Response status: {response.status_code}")
            logger.error(f"Response body: {response.text}")
        
        response.raise_for_status()
        
        logger.info(f"✅ Message sent: {text[:50]}...")
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Failed to send message: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Unexpected error in send_message: {e}")
        return False

def hourly_task():
    """Task that runs every hour."""
    logger.info("⏰ Running hourly task...")
    
    now = datetime.now()
    time_str = now.strftime("%H:%M %d.%m.%Y")
    message = f"💓 *Hourly Update*\n⏰ {time_str}\n\n✅ System is running normally"
    
    send_message(message)

def startup_task():
    """Task that runs once on startup."""
    logger.info("🚀 Running startup task...")
    
    now = datetime.now()
    time_str = now.strftime("%H:%M %d.%m.%Y")
    message = f"🤖 *Bot Started*\n⏰ {time_str}\n\n✅ System is online and monitoring"
    
    send_message(message)

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
        "chat_id": CHAT_ID if CHAT_ID else "not_set",
        "mode": "scheduler_only"
    })

@app.route('/trigger')
def trigger():
    """Manual trigger endpoint for testing."""
    try:
        hourly_task()
        return jsonify({"status": "success", "message": "Task triggered manually"})
    except Exception as e:
        logger.error(f"Error in /trigger: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/send/<message>')
def send_custom(message):
    """Send custom message (for testing)."""
    try:
        success = send_message(message)
        if success:
            return jsonify({"status": "success", "message": f"Sent: {message}"})
        else:
            return jsonify({"status": "error", "message": "Failed to send"}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/test-config')
def test_config():
    """Test bot configuration."""
    try:
        # Test API call to get bot info
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/getMe"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        bot_info = response.json()
        
        return jsonify({
            "status": "success",
            "bot_username": bot_info.get('result', {}).get('username'),
            "bot_id": bot_info.get('result', {}).get('id'),
            "chat_id": CHAT_ID,
            "chat_id_type": type(CHAT_ID).__name__
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e),
            "chat_id": CHAT_ID,
            "chat_id_type": type(CHAT_ID).__name__
        }), 500

def run_flask():
    """Run Flask server."""
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"🌐 Starting Flask server on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

def main():
    """Main function."""
    logger.info("=" * 60)
    logger.info("🤖 TELEGRAM SCHEDULER BOT STARTING")
    logger.info("=" * 60)
    
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
        name='Hourly Telegram Update',
        misfire_grace_time=300  # Allow 5 min grace period
    )
    
    logger.info("✅ Scheduler configured:")
    logger.info("   - Hourly task: Every hour at :00")
    
    # Start scheduler
    scheduler.start()
    logger.info("✅ Scheduler started successfully")
    
    # Run startup task
    try:
        startup_task()
    except Exception as e:
        logger.error(f"❌ Startup task failed: {e}")
    
    # Start Flask in main thread (required by Render)
    logger.info("=" * 60)
    logger.info("🚀 Bot fully initialized")
    logger.info("📡 NO POLLING - Scheduler only mode")
    logger.info("🌐 Starting Flask server...")
    logger.info("=" * 60)
    run_flask()

if __name__ == '__main__':
    main()