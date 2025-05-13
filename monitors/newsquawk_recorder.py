#!/usr/bin/env python3
# monitors/newsquawk_recorder.py

import os
import sys
import time
import json
import tempfile
import wave
import datetime
import logging
import csv

import requests
import websocket
import numpy as np
import pyaudiowpatch as pyaudio
from openai import OpenAI
from utils import Keys  # your local credentials helper

# ── Logging setup ────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)

# ── Credentials ─────────────────────────────────────────────────────────
DISCORD_CHANNEL = 855359994547011604
OPENAI_CLIENT = OpenAI(api_key=Keys.OPENAI_API)
DISCORD_URL = (
    f"https://discord.com/api/v10/channels/"
    f"{DISCORD_CHANNEL}/messages"
)
DISCORD_HEADERS = {
    "Authorization": f"Bot {Keys.DISCORD_BOT_TOKEN}",
    "Content-Type": "application/json"
}

# ── Chrome/CDP settings ──────────────────────────────────────────────────
DEBUG_PORT = 9222
TARGET_URL = "https://newsquawk.com/headlines/list"

# ── VAD & audio parameters ───────────────────────────────────────────────
POLL_INTERVAL = 0.5  # seconds per chunk
SKIP_DURATION = 0.2 # skip clips < 170ms
RMS_THRESHOLD = 500  # speech threshold
SILENCE_DEBOUNCE = 2.5  # seconds of silence to end utterance
MIN_WORDS = 5  # require at least 5 words before posting
# --- new: skip any WAV file smaller than ~32 KB (tune as needed) ---
MIN_FILE_SIZE_BYTES = 32_000

CSV_PATH = os.path.join(os.path.dirname(__file__), "headlines.csv")

def get_ws_url():
    logger.debug("Fetching Chrome tabs on port %d…", DEBUG_PORT)
    try:
        tabs = requests.get(f"http://127.0.0.1:{DEBUG_PORT}/json").json()
    except Exception as e:
        logger.error("Cannot connect to Chrome DevTools: %s", e)
        sys.exit(1)
    tgt = next((t for t in tabs if t.get("url") == TARGET_URL), None)
    if not tgt:
        logger.error("Tab not found: %s", TARGET_URL)
        sys.exit(1)
    logger.debug("Found target tab, WS URL: %s", tgt["webSocketDebuggerUrl"])
    return tgt["webSocketDebuggerUrl"]

# ── Discord posting ───────────────────────────────────────────────────────
def post_to_discord(text: str):
    payload = {
        "embeds": [{"description": text, "color": 0x32CD32}]
    }
    logger.debug("Posting to Discord channel %s: %r", DISCORD_CHANNEL, text)
    r = requests.post(DISCORD_URL, json=payload, headers=DISCORD_HEADERS)
    if r.status_code not in (200, 204):
        logger.warning("Discord post failed: %s %s", r.status_code, r.text)

# ── 1) Connect to Chrome DevTools ────────────────────────────────────────
ws_url = get_ws_url()
logger.info("✅ Connecting to CDP…")
ws = websocket.create_connection(ws_url, origin=f"http://127.0.0.1:{DEBUG_PORT}")
msg_id = 1
ws.send(json.dumps({"id": msg_id, "method": "Runtime.enable"}))
while True:
    m = json.loads(ws.recv())
    if m.get("id") == msg_id:
        logger.debug("CDP Runtime.enable acknowledged")
        break
msg_id += 1

# ── 2) Set up WASAPI loopback ───────────────────────────────────────────
pa = pyaudio.PyAudio()
api_info = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
out_idx = api_info["defaultOutputDevice"]
dev_info = pa.get_device_info_by_index(out_idx)
if not dev_info.get("isLoopbackDevice"):
    for i in range(pa.get_device_count()):
        d = pa.get_device_info_by_index(i)
        if d.get("isLoopbackDevice") and dev_info["name"] in d["name"]:
            dev_info = d
            break

SAMPLE_RATE = int(dev_info["defaultSampleRate"])
CHANNELS = dev_info["maxInputChannels"]
CHUNK = int(SAMPLE_RATE * POLL_INTERVAL)

logger.info(
    "🎧 Capturing via %s (rate=%d, channels=%d, chunk=%d)",
    dev_info["name"], SAMPLE_RATE, CHANNELS, CHUNK
)

stream = pa.open(
    format=pyaudio.paInt16,
    channels=CHANNELS,
    rate=SAMPLE_RATE,
    input=True,
    frames_per_buffer=CHUNK,
    input_device_index=dev_info["index"]
)

# ── 3) Main loop: pure RMS‐based VAD ────────────────────────────────────
logger.info("▶️ Monitoring for speech… Ctrl-C to stop")
try:
    recording = False
    frames = []
    silent_at = None
    start_t = None

    logger.debug(
        "Parameters: RMS_THRESHOLD=%d, SKIP_DURATION=%.3fs, SILENCE_DEBOUNCE=%.3fs, MIN_WORDS=%d",
        RMS_THRESHOLD, SKIP_DURATION, SILENCE_DEBOUNCE, MIN_WORDS
    )

    while True:
        raw = stream.read(CHUNK, exception_on_overflow=False)
        pcm = np.frombuffer(raw, dtype=np.int16)
        rms = int(np.sqrt(np.mean(pcm.astype(np.float32) ** 2)))
        # only log RMS when above threshold
        if rms >= RMS_THRESHOLD:
            logger.info("RMS=%d", rms)

        if not recording:
            if rms >= RMS_THRESHOLD:
                recording = True
                frames = [raw]
                start_t = time.time()
                silent_at = None
                logger.info("🔴 Started recording at %.3f", start_t)
        else:
            frames.append(raw)
            if rms < RMS_THRESHOLD:
                if silent_at is None:
                    silent_at = time.time()
                    logger.debug("Silence detected, debounce starts at %.3f", silent_at)
                elif time.time() - silent_at >= SILENCE_DEBOUNCE:
                    end_t = time.time()
                    duration = end_t - start_t
                    logger.info("Silence debounce passed—stopping at %.3f (%.3fs)", end_t, duration)
                    if duration < SKIP_DURATION:
                        logger.warning("Skipped too-short clip (%.3fs < %.3fs)", duration, SKIP_DURATION)
                    else:
                        tmp = os.path.join(tempfile.gettempdir(), f"nwk_{int(start_t)}.wav")
                        with wave.open(tmp, 'wb') as wf:
                            wf.setnchannels(CHANNELS)
                            wf.setsampwidth(pa.get_sample_size(pyaudio.paInt16))
                            wf.setframerate(SAMPLE_RATE)
                            wf.writeframes(b''.join(frames))
                            file_size = os.path.getsize(tmp)
                        logger.info("🟢 Saved clip (%.2fs) → %s", duration, tmp)
                        if file_size < MIN_FILE_SIZE_BYTES:
                            logger.warning("Skipped too‐small clip (%d bytes)", file_size)
                        else:
                            # transcribe
                            logger.debug("Calling Whisper for transcription…")
                        # transcribe
                        try:
                            logger.debug("Calling Whisper for transcription…")
                            with open(tmp, "rb") as f:
                                resp = OPENAI_CLIENT.audio.transcriptions.create(
                                    model="whisper-1",
                                    file=f,
                                    language="en",
                                    prompt="This is an announcer squawking financial headlines and events, transcribe accurately"
                                )
                            text = resp.text.strip()
                            logger.info("Transcription result: %r", text)
                            if len(text.split()) < MIN_WORDS:
                                logger.warning("Too few words (%d), skipping: %r", len(text.split()), text)
                            else:
                                ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)
                                # append with Source="Squawk"
                                with open(CSV_PATH, "a", newline="", encoding="utf-8") as csvf:
                                    writer = csv.writer(csvf)
                                    writer.writerow([ts, text, "Squawk"])
                                post_to_discord(text)
                        except Exception as e:
                            logger.error("⚠️ Transcription error: %s", e)

                        try:
                            os.remove(tmp)
                            logger.debug("Deleted temp file %s", tmp)
                        except OSError as e:
                            logger.warning("Could not delete temp file: %s", e)

                    recording = False
                    silent_at = None

        time.sleep(POLL_INTERVAL)

except KeyboardInterrupt:
    logger.info("🛑 User stopped")

finally:
    logger.info("💤 Cleaning up…")
    stream.stop_stream()
    stream.close()
    pa.terminate()
    ws.close()
    logger.info("💤 Exiting")
