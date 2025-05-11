#!/usr/bin/env python3
# monitors/audio_headline.py

import os
import sys
import time
import json
import tempfile
import wave
import datetime

import requests
import websocket
import pyaudiowpatch as pyaudio
from openai import OpenAI
from utils import Keys  # only import Keys

# ── Credentials ─────────────────────────────────────────────────────────
OPENAI_API_KEY    = Keys.OPENAI_API
DISCORD_BOT_TOKEN = Keys.DISCORD_BOT_TOKEN

OPENAI_CLIENT     = OpenAI(api_key=OPENAI_API_KEY)
NOTEBOOK_CHANNEL_ID = "855359994547011604"
DISCORD_URL       = f"https://discord.com/api/v10/channels/{NOTEBOOK_CHANNEL_ID}/messages"
DISCORD_HEADERS   = {
    "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
    "Content-Type":  "application/json"
}

# ── Tab & capture settings ──────────────────────────────────────────────
DEBUG_PORT      = 9222
TARGET_URL      = "https://www.youtube.com/watch?v=VhJ9k9Ojyg4"
POLL_INTERVAL   = 0.2    # seconds between checks
MIN_RECORD_TIME = 0.1    # skip very short clips
CSV_PATH        = os.path.join(os.path.dirname(__file__), "headlines.csv")

# ── Helpers ───────────────────────────────────────────────────────────────
def get_ws_url():
    try:
        tabs = requests.get(f"http://127.0.0.1:{DEBUG_PORT}/json").json()
    except Exception as e:
        print("❌ Cannot connect to Chrome DevTools:", e)
        sys.exit(1)
    tgt = next((t for t in tabs if t.get("url")==TARGET_URL), None)
    if not tgt:
        print(f"❌ Tab not found: {TARGET_URL}")
        print(f"   Launch Chrome with --remote-debugging-port={DEBUG_PORT}")
        sys.exit(1)
    return tgt["webSocketDebuggerUrl"]

def post_to_discord(text: str):
    payload = {"embeds":[{"description": text, "color": 0x00ff00}]}
    r = requests.post(DISCORD_URL, json=payload, headers=DISCORD_HEADERS)
    if r.status_code not in (200,204):
        print("⚠️ Discord post failed:", r.status_code, r.text)

# ── 1) Connect to CDP WebSocket ────────────────────────────────────────
ws_url = get_ws_url()
print("✅ Found tab, connecting to CDP…")
# pass origin so Chrome won’t reject us
ws = websocket.create_connection(ws_url, origin=f"http://127.0.0.1:{DEBUG_PORT}")
msg_id = 1
ws.send(json.dumps({"id": msg_id, "method": "Runtime.enable"}))
# wait for enable response
while True:
    m = json.loads(ws.recv())
    if m.get("id")==msg_id:
        break
msg_id += 1

def is_playing():
    global msg_id
    expr = ("Array.from(document.querySelectorAll('video,audio'))"
            ".some(e=>!e.paused)")
    ws.send(json.dumps({
        "id": msg_id,
        "method": "Runtime.evaluate",
        "params": {"expression": expr, "returnByValue": True}
    }))
    this_id = msg_id
    msg_id += 1

    while True:
        m = json.loads(ws.recv())
        if m.get("id")==this_id:
            return bool(m["result"]["result"]["value"])

# ── 2) Setup WASAPI loopback ────────────────────────────────────────────
pa       = pyaudio.PyAudio()
api_info = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
out_idx  = api_info["defaultOutputDevice"]
dev_info = pa.get_device_info_by_index(out_idx)
if not dev_info.get("isLoopbackDevice"):
    for i in range(pa.get_device_count()):
        d = pa.get_device_info_by_index(i)
        if d.get("isLoopbackDevice") and dev_info["name"] in d["name"]:
            dev_info = d
            break

SAMPLE_RATE = int(dev_info["defaultSampleRate"])
CHANNELS    = dev_info["maxInputChannels"]
CHUNK       = int(SAMPLE_RATE * POLL_INTERVAL)

stream = pa.open(
    format=pyaudio.paInt16,
    channels=CHANNELS,
    rate=SAMPLE_RATE,
    input=True,
    frames_per_buffer=CHUNK,
    input_device_index=dev_info["index"]
)
print(f"🎧 Capturing via {dev_info['name']} (loopback)")

# ── 3) Main loop: record only when page media is playing ───────────────
print("▶️ Monitoring for playback... Ctrl-C to stop")
try:
    while True:
        # wait for play
        while not is_playing():
            time.sleep(POLL_INTERVAL)

        print("🔴 Playback detected—recording")
        frames = []
        start = time.time()

        while is_playing():
            frames.append(stream.read(CHUNK, exception_on_overflow=False))

        duration = time.time() - start
        if duration < MIN_RECORD_TIME:
            print(f"⚠️ Skipped clip ({duration:.2f}s)")
            continue

        print(f"🟢 Playback ended ({duration:.2f}s), saving…")
        tmp = os.path.join(tempfile.gettempdir(), f"nwk_{int(time.time())}.wav")
        with wave.open(tmp,'wb') as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(pa.get_sample_size(pyaudio.paInt16))
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(b''.join(frames))

        # ── 4) Transcribe ───────────────────────────────────────────────
        try:
            with open(tmp,"rb") as f:
                resp = OPENAI_CLIENT.audio.transcriptions.create(
                    model="whisper-1", file=f
                )
            text = resp.text.strip()
            print("   ↳", text)
        except Exception as e:
            print("⚠️ Transcription error:", e)
            text = None

        # ── 5) Log & post ───────────────────────────────────────────────
        if text:
            ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)
            with open(CSV_PATH,"a",encoding="utf-8") as csvf:
                csvf.write(f"{ts},{text}\n")
            post_to_discord(text)

        try: os.remove(tmp)
        except: pass

except KeyboardInterrupt:
    print("\n🛑 User stopped")

finally:
    stream.stop_stream()
    stream.close()
    pa.terminate()
    ws.close()
    print("💤 Exiting")
