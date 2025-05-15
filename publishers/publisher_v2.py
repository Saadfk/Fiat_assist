#!/usr/bin/env python3
import os
import time
import re
import datetime
import requests
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from utils.Keys import DISCORD_BOT_TOKEN
from utils.usage_tracker import UsageTracker
from utils.headline_aggregator import HeadlineAggregator
from publisher import post_to_twitter

# --- Configuration ---
DISCORD_CHANNEL_ID = 855359994547011604
CSV_FILE           = "headlines.csv"

# Map of Source → embed color
COLOR_MAP = {
    "RTRS":   0xFFA500,  # Orange
    "FLY":    0x0000FF,  # Blue
    "SQUAWK": 0x32CD32,  # LimeGreen
}

# Flag: wrap all embed text in bold
EMBED_BOLD = True

# Twitter usage limiter
twitter_usage = UsageTracker(
    usage_file="tweet_usage.json",
    max_attempts=100,
    time_window=24 * 3600
)

# Buffered aggregator
aggregator = HeadlineAggregator(flush_interval=5)


class HeadlinesHandler(FileSystemEventHandler):
    def __init__(self, watch_dir):
        super().__init__()
        self.watch_dir = watch_dir
        self.file_path = os.path.join(watch_dir, CSV_FILE)
        self.offset = os.path.getsize(self.file_path) if os.path.exists(self.file_path) else 0
        self.posted = set()

    def on_modified(self, event):
        if event.is_directory:
            return
        if os.path.abspath(event.src_path) != os.path.abspath(self.file_path):
            return
        self._process_new_lines()

    def _process_new_lines(self):
        if not os.path.exists(self.file_path):
            return

        new_size = os.path.getsize(self.file_path)
        if new_size < self.offset:
            self.offset = 0
            self.posted.clear()
        if new_size == self.offset:
            return

        with open(self.file_path, "r", encoding="utf-8") as f:
            f.seek(self.offset)
            chunk = f.read()
        self.offset = new_size

        for raw in chunk.splitlines():
            line = raw.strip()
            if not line:
                continue

            # strip leading timestamp
            line = re.sub(
                r'^\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}(?:\.\d+)?,\s*',
                "",
                line
            ).strip()

            # split off Source
            parts = line.rsplit(",", 1)
            if len(parts) == 2:
                headline, source = parts[0].strip(), parts[1].strip().upper()
            else:
                headline, source = line, None

            if headline in self.posted:
                continue
            self.posted.add(headline)

            aggregator.add_line(headline)

            ts = datetime.datetime.now().strftime("%H:%M")
            text = f"[{ts}] {headline}"
            if EMBED_BOLD:
                text = f"**{text}**"

            color = COLOR_MAP.get(source or "", 0)
            embed = {
                "description": text,
                "color": color
            }
            post_to_discord(DISCORD_CHANNEL_ID, embed=embed)
            print(f"[{ts}] {headline}")


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

    resp = requests.post(url, headers=headers, json=payload)
    if resp.status_code not in (200, 201):
        print(f"Discord error {resp.status_code}: {resp.text}")


def main():
    project_root = os.path.dirname(os.path.dirname(__file__))
    monitors_dir = os.path.join(project_root, "monitors")

    if not os.path.isdir(monitors_dir):
        raise FileNotFoundError(f"Monitors folder not found: {monitors_dir}")

    handler = HeadlinesHandler(monitors_dir)
    observer = Observer()
    observer.schedule(handler, monitors_dir, recursive=False)
    observer.start()
    print("Watching:", os.path.join(monitors_dir, CSV_FILE))

    # try:
    #     while True:
    #         time.sleep(1)
    #         if aggregator.should_flush():
    #             combined = aggregator.flush()
    #             if len(combined) > 280:
    #                 combined = combined[:280] + "..."
    #             if twitter_usage.can_post():
    #                 twitter_usage.record_post()
    #                 ts = datetime.datetime.now().strftime("%H:%M")
    #                 post_to_twitter(f"[{ts}]\n{combined}")
    #             else:
    #                 print("SKIPPED TWEET (limit reached).")
    # except KeyboardInterrupt:
    #     observer.stop()
    observer.join()


if __name__ == "__main__":
    main()