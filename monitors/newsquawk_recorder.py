#!/usr/bin/env python3
# monitors/newsquawk_recorder.py
# Launch Chrome like:
# "C:\Program Files\Google\Chrome\Application\chrome.exe" ^
#   --remote-debugging-port=9222 --remote-allow-origins=* ^
#   --user-data-dir="%LOCALAPPDATA%\Temp\chrome-debug-profile"

import os
import sys
import time
import json
import tempfile
import wave
import datetime

import requests
import websocket
import numpy as np
import pyaudiowpatch as pyaudio
from openai import OpenAI
from utils import Keys  # only import Keys

# ── Credentials ─────────────────────────────────────────────────────────
OPENAI_API_KEY       = Keys.OPENAI_API
DISCORD_BOT_TOKEN    = Keys.DISCORD_BOT_TOKEN
NOTEBOOK_CHANNEL_ID  = "1369841053649207347"
DISCORD_URL          = f"https://discord.com/api/v10/channels/{NOTEBOOK_CHANNEL_ID}/messages"
DISCORD_HEADERS      = {
    "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
    "Content-Type":  "application/json"
}
OPENAI_CLIENT        = OpenAI(api_key=OPENAI_API_KEY)

# ── Tab & capture settings ──────────────────────────────────────────────
DEBUG_PORT       = 9222
TARGET_URL       = "https://newsquawk.com/headlines/list"
POLL_INTERVAL    = 0.2     # seconds per audio chunk
SKIP_DURATION    = 0.05    # skip any clip shorter than 50ms
CSV_PATH         = os.path.join(os.path.dirname(__file__), "headlines.csv")

# ── VAD parameters ────────────────────────────────────────────────────────
RMS_THRESHOLD    = 500     # adjust until RMS jumps on speech
SILENCE_DEBOUNCE = 2.0     # seconds of continuous silence to end utterance
MIN_WORDS        = 4       # minimal words to consider a valid headline

def get_ws_url():
    try:
        tabs = requests.get(f"http://127.0.0.1:{DEBUG_PORT}/json").json()
    except Exception as e:
        print("❌ Cannot connect to Chrome DevTools:", e)
        sys.exit(1)
    target = next((t for t in tabs if t.get("url") == TARGET_URL), None)
    if not target:
        print(f"❌ Tab not found: {TARGET_URL}")
        sys.exit(1)
    return target["webSocketDebuggerUrl"]

def post_to_discord(text: str):
    # lime green embed color
    payload = {"embeds":[{"description": text, "color": 0x32CD32}]}
    r = requests.post(DISCORD_URL, json=payload, headers=DISCORD_HEADERS)
    if r.status_code not in (200, 204):
        print("⚠️ Discord post failed:", r.status_code, r.text)

def main():
    # 1) Connect to Chrome DevTools
    ws_url = get_ws_url()
    print("✅ Connecting to CDP…")
    ws = websocket.create_connection(ws_url, origin=f"http://127.0.0.1:{DEBUG_PORT}")
    msg_id = 1
    ws.send(json.dumps({"id": msg_id, "method": "Runtime.enable"}))
    while True:
        m = json.loads(ws.recv())
        if m.get("id") == msg_id:
            break
    msg_id += 1

    # 2) Set up WASAPI loopback
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

    # 3) Main loop: RMS-based VAD with silence debounce
    print("▶️ Monitoring for speech… Ctrl-C to stop")
    try:
        recording    = False
        frames       = []
        silent_start = None
        start_time   = None

        while True:
            raw = stream.read(CHUNK, exception_on_overflow=False)
            pcm = np.frombuffer(raw, dtype=np.int16)
            rms = int(np.sqrt(np.mean(pcm.astype(np.float32)**2)))
            if rms > 0:
                print(f"[DEBUG] chunk RMS={rms}")

            if not recording:
                if rms >= RMS_THRESHOLD:
                    recording    = True
                    frames       = [raw]
                    start_time   = time.time()
                    silent_start = None
                    print("🔴 Speech detected—start recording")
            else:
                frames.append(raw)
                if rms < RMS_THRESHOLD:
                    if silent_start is None:
                        silent_start = time.time()
                    elif time.time() - silent_start >= SILENCE_DEBOUNCE:
                        # end of utterance
                        duration = time.time() - start_time
                        recording    = False
                        silent_start = None

                        # skip too-short clips
                        if duration < SKIP_DURATION:
                            print(f"⚠️ Skipped too-short clip ({duration:.3f}s)")
                            continue

                        # save WAV
                        tmp = os.path.join(
                            tempfile.gettempdir(),
                            f"nwk_{int(start_time)}.wav"
                        )
                        with wave.open(tmp, 'wb') as wf:
                            wf.setnchannels(CHANNELS)
                            wf.setsampwidth(pa.get_sample_size(pyaudio.paInt16))
                            wf.setframerate(SAMPLE_RATE)
                            wf.writeframes(b''.join(frames))
                        print(f"🟢 Saved clip ({duration:.2f}s) → {tmp}")

                        # transcribe
                        try:
                            with open(tmp, "rb") as f:
                                resp = OPENAI_CLIENT.audio.transcriptions.create(
                                    model="whisper-1", file=f
                                )
                            text = resp.text.strip()
                        except Exception as e:
                            print("⚠️ Transcription error:", e)
                            text = None

                        # skip trivial one-word results
                        if text and len(text.split()) >= MIN_WORDS:
                            print("   ↳", text)
                            # log to CSV
                            ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)
                            with open(CSV_PATH, "a", encoding="utf-8") as csvf:
                                csvf.write(f"{ts},{text}\n")
                            # post to Discord
                            post_to_discord(text)
                        elif text:
                            print(f"⚠️ Skipping trivial transcription: '{text}'")

                        # clean up
                        try:
                            os.remove(tmp)
                        except OSError:
                            pass

            time.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        print("\n🛑 User stopped")

    finally:
        print("💤 Cleaning up…")
        stream.stop_stream()
        stream.close()
        pa.terminate()
        ws.close()
        print("💤 Exiting")

if __name__ == "__main__":
    main()
