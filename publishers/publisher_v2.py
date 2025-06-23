#!/usr/bin/env python3
# publisher_discord_lastrow.py – watch headlines1.csv and push newest row to Discord

import asyncio, os, re, datetime, collections, sys
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# ── YOUR ORIGINAL helper ──────────────────────────────────────────────────
# (verbatim copy – nothing changed)
import requests
from utils.Keys import DISCORD_BOT_TOKEN

def post_to_discord(channel_id, message=None, embed=None):
    url = f"https://discord.com/api/channels/{channel_id}/messages"
    headers = {
        "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {"content": message} if embed is None else {"embeds": [embed]}
    resp = requests.post(url, headers=headers, json=payload)
    if resp.status_code not in (200, 201):
        print(f"Discord error {resp.status_code}: {resp.text}", flush=True)

# ─── Configuration ───────────────────────────────────────────────────────
PROJECT_ROOT       = Path(__file__).resolve().parents[1]      # …/Fiat_assist
CSV_FILE           = PROJECT_ROOT / "monitors" / "headlines1.csv"
DISCORD_CHANNEL_ID = 855359994547011604

COLOR_MAP  = {"RTRS": 0xFFA500, "FLY": 0x0000FF, "SQUAWK": 0x32CD32}
EMBED_BOLD = True
DEDUP_MAX  = 40_000

TS_RE  = re.compile(r'^\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}(?:\.\d+)?,\s*')
SRC_RE = re.compile(r',\s*([^,]+)$')

def dbg(msg):
    now = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"[{now}] {msg}", flush=True)

# ─── Watchdog handler ────────────────────────────────────────────────────
class HeadlinesHandler(FileSystemEventHandler):
    def __init__(self, loop, queue, dedup):
        self.loop   = loop
        self.queue  = queue
        self.dedup  = dedup
        self.offset = CSV_FILE.stat().st_size if CSV_FILE.exists() else 0
        dbg(f"Start offset {self.offset:,} bytes")

    def on_modified(self, ev):
        if ev.is_directory or Path(ev.src_path) != CSV_FILE:
            return
        self._read_tail()

    # --------------------------------------------------------------------
    def _read_tail(self):
        size = CSV_FILE.stat().st_size
        if size < self.offset:                 # file rotated/truncated
            dbg("Rotation detected → jump to end")
            self.offset = size
            self.dedup.clear()
            return

        if size == self.offset:
            return

        with CSV_FILE.open("r", encoding="utf-8") as f:
            f.seek(self.offset)
            chunk = f.read()
        self.offset = size

        # -------- process only the very last non-blank line -------------
        lines = [l.strip() for l in chunk.splitlines() if l.strip()]
        if not lines:
            return
        line = lines[-1]

        line = TS_RE.sub("", line)
        m = SRC_RE.search(line)
        headline, source = (line[:m.start()].strip(), m.group(1).upper()) if m else (line, "")

        if headline in self.dedup:
            dbg("Duplicate skipped")
            return
        self.dedup.append(headline)

        now  = datetime.datetime.now().strftime("%H:%M")
        text = f"[{now}] {headline}"
        if EMBED_BOLD:
            text = f"**{text}**"
        embed = {"description": text, "color": COLOR_MAP.get(source, 0)}

        dbg(f"Queued: {headline[:80]}…")
        asyncio.run_coroutine_threadsafe(self.queue.put(embed), self.loop)

# ─── Discord worker (async) – uses your helper in a thread ---------------
async def discord_worker(queue):
    dbg("Discord worker ready")
    while True:
        embed = await queue.get()
        await asyncio.to_thread(post_to_discord, DISCORD_CHANNEL_ID, embed=embed)
        queue.task_done()
        dbg("Posted ✓")

# ─── Main async app -------------------------------------------------------
async def app():
    if not CSV_FILE.exists():
        dbg(f"File not found: {CSV_FILE}")
        sys.exit(1)

    queue = asyncio.Queue()
    dedup = collections.deque(maxlen=DEDUP_MAX)

    loop = asyncio.get_running_loop()
    handler = HeadlinesHandler(loop, queue, dedup)
    obs = Observer(); obs.schedule(handler, str(CSV_FILE.parent)) ; obs.start()
    dbg(f"Watching {CSV_FILE}")

    try:
        await discord_worker(queue)            # runs forever
    finally:
        obs.stop(); obs.join()

# ─── Entry-point ----------------------------------------------------------
if __name__ == "__main__":
    try:
        asyncio.run(app())
    except KeyboardInterrupt:
        dbg("Stopped by user")
