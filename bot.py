import logging
import os
import asyncio
import json
import requests
import pytz
from datetime import datetime, time, date

from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, JobQueue
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json?version=d488bf59628ffcced26a7ccaf3f3b70b"

#
#Unemployment Rate / Claims
#ADP/Non-Farm Employment Change
#US GDP (Advance, Preliminary, Final)
#US Consumer Price Index (CPI)
#US ISM Services PMI
#US ISM Manufacturing PMI
#JOLTS Job Openings
#Producer Price Index (PPI)
#US Retail Sales
#Flash Services PMI
#FOMC Statement / Meeting Announcement
#FOMC Minutes / Press Conference / Speech

TOPICS = [
    "Unemployment Rate",
    "Unemployment Claims",
    "ADP Employment Change",
    "Employment Change",
    "Non-Farm Employment Change",
    "GDP",
    "GDP Advance",
    "GDP Advance",
    "GDP Advance",
    "Consumer Price Index",
    "CPI",
    "ISM",
    "ISM Services PMI",
    "ISM Manufacturing PMI",
    "JOLTS",
    "Producer Price Index",
    "PPI",
    "Retail Sales",
    "Flash Services PMI",
    "PMI",
    "FOMC",
    "Fed Interest Rate Decision"
]

# Global Cache
CACHE_DURATION = 3600  # 1 hour in seconds
last_fetch_time = 0
cached_data = []

def fetch_events():
    """Fetch events from the JSON endpoint with caching and error handling."""
    global last_fetch_time, cached_data
    
    now = datetime.now().timestamp()
    
    # Check cache
    if cached_data and (now - last_fetch_time < CACHE_DURATION):
        logger.info(f"Using cached data. Next fetch allowed in {int(CACHE_DURATION - (now - last_fetch_time))} seconds.")
        return cached_data

    try:
        logger.info("Fetching new data from API...")
        response = requests.get(URL, timeout=10)
        response.raise_for_status()
        
        # Try parsing JSON
        data = response.json()
        
        # Update cache on success
        cached_data = data
        last_fetch_time = now
        logger.info(f"Cache updated. Total events: {len(data)}")
        
        return data

    except json.JSONDecodeError:
        logger.error("Failed to parse JSON. Likely rate limited.")
        logger.error(f"Response content: {response.text[:200]}...") # Log first 200 chars
        return [] # Return empty list, don't crash. 
        # Ideally we could return cached_data even if expired if we have it? 
        # For now, safe default is empty to avoid reporting garbage.
        
    except Exception as e:
        logger.error(f"Error fetching events: {e}")
        return []

def filter_events(events):
    """Filter events for USD and matching topics."""
    filtered = []
    for event in events:
        if event.get('country') != 'USD':
            continue
        
        # Case insensitive match
        title = event.get('title', '').lower()
        matched = False
        for topic in TOPICS:
            if topic.lower() in title:
                matched = True
                break
        
        if matched:
            filtered.append(event)
    return filtered

def format_event(event):
    """Format a single event for the message."""
    date_str = event.get('date', 'Unknown Date')
    try:
        dt = datetime.fromisoformat(date_str)
        date_display = dt.strftime("%H:%M %d.%m.%Y")
    except ValueError:
        date_display = date_str

    return (
        f"📅 *{event.get('title')}*\n"
        f"⏰ {date_display}\n"
        f"💥 Impact: {event.get('impact')}\n"
        f"🔮 Forecast: {event.get('forecast', 'N/A')}\n"
        f"🔙 Previous: {event.get('previous', 'N/A')}"
    )

def get_today_events(events):
    """Filter events happening today."""
    today = date.today()
    today_events = []
    for event in events:
        date_str = event.get('date')
        try:
            # Parse date and convert to local date object (ignore time/tz for simple day check or handle correctly)
            # The JSON date is "2025-12-07T18:30:00-05:00". timezone aware.
            # We want to check if it matches 'today' in the user's/bot's timezone?
            # User didn't specify timezone, but data has offset. 
            # Let's assume we care about the local date of the event itself? 
            # Or the date in UTC?
            # Standard practice: Check if the event date matches 'today' in New York time usually for USD data.
            # But let's stick to simple comparison:
            dt = datetime.fromisoformat(date_str)
            if dt.date() == today:
                 today_events.append(event)
        except ValueError:
            continue
    return today_events

async def send_events(context: ContextTypes.DEFAULT_TYPE, event_list, header_text):
    """Helper to send a list of events to the chat."""
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not chat_id:
        logger.warning("TELEGRAM_CHAT_ID not set. Cannot send notification.")
        return

    if not event_list:
        logger.info("No events to send.")
        return

    message_buffer = []
    for event in event_list:
        message_buffer.append(format_event(event))
    
    full_message = f"{header_text}\n\n" + "\n\n".join(message_buffer)
    
    # Simple split if too long (very basic implementation)
    if len(full_message) > 4000:
        await context.bot.send_message(chat_id=chat_id, text=header_text, parse_mode='Markdown')
        for msg in message_buffer:
            await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode='Markdown')
    else:
        await context.bot.send_message(chat_id=chat_id, text=full_message, parse_mode='Markdown')

async def daily_job(context: ContextTypes.DEFAULT_TYPE):
    """Job to run daily to check for today's events."""
    logger.info("Running daily job...")
    events = fetch_events()
    if not events:
        return
    
    filtered = filter_events(events)
    # Check for events happening TODAY
    # Note: 'today' depends on machine time. Docker container should ideally be set to correct TZ or we handle it in code.
    # If the JSON dates are e.g. -05:00, we should probably check if that time falls within 'today' in NY?
    # For now, we'll use the date component of the event string as the source of truth for "Day of event".
    
    # We re-parse to be safe or just string match? String match is risky if TZ shifts.
    # Let's use datetime comparison.
    
    today_events = []
    now = datetime.now() 
    
    # We'll use the server's local date for "today".
    target_date = now.date()
    
    for event in filtered:
        try:
             # The date in JSON is ISO format with offset
             dt = datetime.fromisoformat(event['date'])
             # Compare the date part. 
             # Note: dt.date() is the local date of that timestamp (which includes offset). 
             # So 18:30-05:00 is indeed that day in that timezone.
             if dt.date() == target_date:
                 today_events.append(event)
        except Exception:
            continue
            
    if today_events:
        await send_events(context, today_events, f"📢 **Today's Economic Events ({target_date})**")
    else:
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
        await context.bot.send_message(chat_id=chat_id, text=f"No economic events scheduled for {target_date}", parse_mode='Markdown')

        

async def weekly_job(context: ContextTypes.DEFAULT_TYPE):
    """Job to run weekly (Monday) to show the week's schedule."""
    logger.info("Running weekly job...")
    events = fetch_events()
    filtered = filter_events(events)
    
    if filtered:
        await send_events(context, filtered, "📅 **Weekly Economic Schedule**")

async def heartbeat_job(context: ContextTypes.DEFAULT_TYPE):
    """Job to run every hour to show heartbeat."""
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not chat_id:
        return
        
    now = datetime.now()
    time_str = now.strftime("%H:%M %d.%m.%Y")
    await context.bot.send_message(chat_id=chat_id, text=f"💓 Heartbeat: {time_str}", parse_mode='Markdown')

async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for the /check command (manual check)."""
    await update.message.reply_text("Fetching latest data...")
    events = fetch_events()
    filtered = filter_events(events)
    
    if not filtered:
        await update.message.reply_text("No matching USD events found for this week.")
        return
        
    # Reuse send logic but reply to the command sender, not the configured group 
    # (unless called in the group, which reply handles automatically)
    message_buffer = []
    for event in filtered:
        message_buffer.append(format_event(event))
        
    full_message = "\n\n".join(message_buffer)
    if len(full_message) > 4000:
          for msg in message_buffer:
              await update.message.reply_text(msg, parse_mode='Markdown')
    else:
        await update.message.reply_text(full_message, parse_mode='Markdown')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hello! I am the Economic Calendar Bot.\n"
        "I will post daily updates and a weekly schedule to the configured group."
    )

def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token or token == "your_token_here":
        logger.error("Error: TELEGRAM_BOT_TOKEN not found.")
        return

    application = ApplicationBuilder().token(token).build()
    
    # Setup JobQueue
    job_queue = application.job_queue
    
    # Time for daily report (e.g., 08:00 AM)
    # Using a default time if not specified.
    # Note: Docker container might be UTC. 08:00 UTC.
    job_queue.run_daily(daily_job, time=time(hour=8, minute=0, second=0))
    
    # Time for weekly report (Monday at 08:00 AM)
    # run_daily with 'days' argument? No, run_daily runs every day. 
    # We use run_repeating or run_daily with day filter? 
    # telegram.ext.JobQueue.run_daily supports 'days' tuple. 
    # days=(1,) for Tuesday? 0=Monday? python-telegram-bot uses 0-6 w/ 0=Monday? 
    # Let's check docs or assume standard 0=Mon.
    # Yes, usually days=(0,).
    job_queue.run_daily(weekly_job, time=time(hour=8, minute=0, second=0), days=(0,))

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("check", check_command))

    logger.info("Bot is polling...")
    
    # Start dummy web server for Render
    from flask import Flask
    from threading import Thread

    app = Flask(__name__)

    @app.route('/')
    def health_check():
        return "Alive"

    def run_web():
        port = int(os.environ.get("PORT", 8080))
        app.run(host='0.0.0.0', port=port)

    # Run Flask in a separate thread
    t = Thread(target=run_web)
    t.daemon = True
    t.start()

    application.run_polling()

if __name__ == '__main__':
    main()
