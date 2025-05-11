import os
import time
import csv
import re
import datetime
import requests
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from utils.Keys import DISCORD_BOT_TOKEN
from utils.usage_tracker import UsageTracker
from utils.headline_aggregator import HeadlineAggregator
from publisher import post_to_twitter

# Target Discord channel ID for posting individual embed messages
DISCORD_CHANNEL_ID = 855359994547011604

# The CSV files we want to monitor (these are located in the monitors folder)
CSV_FILES_TO_WATCH = ["headlines.csv", "flylines.csv"]

# Create a usage tracker (e.g., limit to 100 tweets in 24 hours)
twitter_usage = UsageTracker(
    usage_file="tweet_usage.json",
    max_attempts=100,
    time_window=24 * 3600
)

# Create a headline aggregator with a flush interval (in seconds)
aggregator = HeadlineAggregator(flush_interval=5)


class MultiCSVHandler(FileSystemEventHandler):
    def __init__(self, csv_files, watch_dir):
        super().__init__()
        self.csv_files = csv_files
        self.watch_dir = watch_dir  # store the watch directory path
        self.file_offsets = {}
        self.posted_lines = {}
        for f in csv_files:
            file_path = os.path.join(self.watch_dir, f)
            if os.path.exists(file_path):
                self.file_offsets[f] = os.path.getsize(file_path)
            else:
                self.file_offsets[f] = 0
            self.posted_lines[f] = set()

    def on_modified(self, event):
        file_name = os.path.basename(os.path.abspath(event.src_path))
        if file_name in self.csv_files:
            self.process_new_lines(file_name)

    def process_new_lines(self, file_name):
        file_path = os.path.join(self.watch_dir, file_name)
        if not os.path.exists(file_path):
            print(f"File {file_name} not found, skipping.")
            return

        current_offset = self.file_offsets.get(file_name, 0)
        new_offset = os.path.getsize(file_path)

        # Handle file truncation
        if new_offset < current_offset:
            current_offset = 0
            self.posted_lines[file_name].clear()

        if new_offset > current_offset:
            with open(file_path, "r", encoding="utf-8") as f:
                f.seek(current_offset)
                new_data = f.read()
                self.file_offsets[file_name] = new_offset  # update offset

            lines = new_data.splitlines()
            for line in lines:
                if line.strip():
                    # Remove any leading timestamp (e.g. "2025-02-27T15:45:30, " or similar)
                    pattern = r'^\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}(?:\.\d+)?,\s*'
                    cleaned_line = re.sub(pattern, '', line).strip()

                    # For flylines.csv, remove the "Fly " prefix if present
                    if file_name == "flylines.csv" and cleaned_line.startswith("Fly "):
                        cleaned_line = cleaned_line[len("Fly "):].strip()

                    # Skip if this line has already been posted
                    if cleaned_line in self.posted_lines[file_name]:
                        continue
                    self.posted_lines[file_name].add(cleaned_line)

                    # Add the cleaned line to the aggregator
                    aggregator.add_line(cleaned_line)

                    # Post individual Discord embed:
                    hhmm = datetime.datetime.now().strftime("%H:%M")
                    if file_name == "headlines.csv":
                        title = "RTRS"
                        color = 16753920  # Orange
                    elif file_name == "flylines.csv":
                        title = "FLY"
                        color = 255  # Blue
                    else:
                        title = file_name
                        color = 0
                    embed = {
                        "title": title,
                        "description": f"[{hhmm}] {cleaned_line}",
                        "color": color
                    }
                    post_to_discord(DISCORD_CHANNEL_ID, embed=embed)
                    print(f"[{hhmm}] {file_name} -> {cleaned_line}")


def post_to_discord(channel_id, message=None, embed=None):
    url = f"https://discord.com/api/channels/{channel_id}/messages"
    headers = {
        "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {}
    if embed:
        payload["embeds"] = [embed]
    else:
        payload["content"] = message
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code not in (200, 201):
        print(f"ERROR posting to Discord: {response.status_code} {response.text}")


def main():
    # Set the watch directory to the monitors folder
    watch_dir = r"C:\Users\User\PycharmProjects\Fiat_assist"
    event_handler = MultiCSVHandler(CSV_FILES_TO_WATCH, watch_dir)

    observer = Observer()
    observer.schedule(event_handler, watch_dir, recursive=False)
    observer.start()

    print("Monitoring CSV changes in:", watch_dir)
    try:
        while True:
            time.sleep(1)
            # Check if aggregator is ready to flush its buffered headlines
            if aggregator.should_flush():
                combined_message = aggregator.flush()
                if len(combined_message) > 280:
                    combined_message = combined_message[:280] + "..."
                if twitter_usage.can_post():
                    twitter_usage.record_post()
                    hhmm = datetime.datetime.now().strftime("%H:%M")
                    tweet_message = f"[{hhmm}]\n{combined_message}"
                    #post_to_twitter(tweet_message)
                else:
                    print("SKIPPED TWEET (limit reached).")
    except KeyboardInterrupt:
        print("Stopping observer...")
        observer.stop()
    observer.join()


if __name__ == "__main__":
    main()
