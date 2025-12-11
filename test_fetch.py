import requests
import json
from datetime import datetime

URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json?version=d488bf59628ffcced26a7ccaf3f3b70b"

TOPICS = [
    "Unemployment Rate",
    "Unemployment Claims",
    "ADP",
    "Non-Farm Employment Change",
    "GDP",
    "Consumer Price Index",
    "CPI",
    "ISM Services PMI",
    "ISM Manufacturing PMI",
    "JOLTS",
    "Producer Price Index",
    "PPI",
    "Retail Sales",
    "Flash Services PMI",
    "FOMC",
    "Fed Interest Rate Decision"
]

def fetch_events():
    response = requests.get(URL)
    response.raise_for_status()
    return response.json()

def filter_events(events):
    filtered = []
    for event in events:
        if event.get('country') != 'USD':
            continue
        
        title = event.get('title', '').lower()
        # Check if any topic matches
        matched = False
        for topic in TOPICS:
            # Simple substring match, case insensitive
            if topic.lower() in title:
                matched = True
                break
        
        if matched:
            filtered.append(event)
    return filtered

if __name__ == "__main__":
    print("Fetching events...")
    try:
        events = fetch_events()
        print(f"Total events: {len(events)}")
        
        usd_filtered = filter_events(events)
        print(f"Filtered USD events matching topics: {len(usd_filtered)}")
        
        for event in usd_filtered:
            print(f"- {event['date']}: {event['title']} (Impact: {event.get('impact')})")
            
    except Exception as e:
        print(f"Error: {e}")
