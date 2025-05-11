import time
import csv
import datetime
import logging
import re
import requests
from pywinauto import Desktop, Application
from utils.Keys import DISCORD_BOT_TOKEN, NOTEBOOK_CHANNEL_ID

POLL_INTERVAL = 1
WINDOW_TITLE = "FIATFEED"
MAX_ATTEMPTS = 10

logging.basicConfig(
    filename="fiatfeed_monitor.log",
    level=logging.INFO,
    format="%(asctime)s - %(message)s"
)

def log_message(message):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {message}")
    logging.info(message)

def beep():
    try:
        import winsound
        winsound.Beep(550, 200)
    except ImportError:
        print("winsound not available.")

def find_window_pid():
    for w in Desktop(backend="uia").windows():
        try:
            if WINDOW_TITLE in w.window_text():
                pid = w.process_id()
                log_message(f"Found window '{w.window_text()}' with PID {pid}.")
                return pid
        except Exception:
            continue
    return None

def is_all_upper(text):
    filtered = ''.join(c for c in text if c.isalpha())
    return bool(filtered) and filtered == filtered.upper()

def words_mostly_upper(text, threshold=0.75):
    words = text.split()
    if not words:
        return False, 0.0
    count = sum(1 for word in words if word.isupper())
    ratio = count / len(words)
    return ratio >= threshold, ratio

def extract_headline(full_text):
    pattern = re.compile(r'(\d{2}:\d{2}:\d{2})\s+((?:(?!\d{2}:\d{2}:\d{2}).)+)', re.DOTALL)
    for _, candidate in pattern.findall(full_text):
        candidate = candidate.strip()
        if len(candidate.split()) < 5:
            continue
        if is_all_upper(candidate):
            return candidate
        passes, _ = words_mostly_upper(candidate)
        if passes:
            return candidate
    return None

def post_to_discord(message):
    url = f"https://discord.com/api/v9/channels/{NOTEBOOK_CHANNEL_ID}/messages"
    headers = {"Authorization": f"Bot {DISCORD_BOT_TOKEN}", "Content-Type": "application/json"}
    payload = {"content": message}
    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
    except Exception as e:
        log_message(f"Discord post failed: {e}")

def log_headline_csv(headline):
    with open("headlines.csv", "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), headline])

def monitor_control(control, main_window):
    spinner = ['|', '/', '-', '\\']
    index = 0
    seen = set(control.window_text().splitlines())
    log_message("Monitoring control for updates...")
    while True:
        time.sleep(POLL_INTERVAL)
        if not main_window.exists():
            log_message(f"Window '{WINDOW_TITLE}' no longer exists.")
            break
        try:
            current_text = control.window_text()
        except Exception as e:
            log_message(f"Error reading control: {e}")
            break
        current_lines = [line for line in current_text.splitlines() if line.strip()]
        new_lines = [ln for ln in current_lines if ln not in seen]
        for ln in new_lines:
            seen.add(ln)
        if new_lines:
            beep()
            try:
                with open("control_dump.csv", "a", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow([datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
                    for line in current_text.splitlines():
                        writer.writerow([line])
                    writer.writerow([])
            except Exception as e:
                log_message(f"Dump error: {e}")
            headline = extract_headline(current_text)
            if headline:
                log_message(f"Extracted headline: {headline}")
                log_headline_csv(headline)
                # Uncomment to post headline to Discord:
                # post_to_discord(headline)
            else:
                log_message("No valid headline extracted.")
        else:
            print(f"Monitoring {spinner[index]}", end='\r', flush=True)
            index = (index + 1) % len(spinner)

def monitor_window():
    pid = find_window_pid()
    if not pid:
        log_message(f"Window '{WINDOW_TITLE}' not found.")
        return
    try:
        app = Application(backend="uia").connect(process=pid)
        main_window = app.window(title_re=".*" + WINDOW_TITLE + ".*")
    except Exception as e:
        log_message(f"Error connecting to window: {e}")
        return
    time.sleep(2)
    try:
        controls = main_window.descendants()
        if len(controls) > 3:
            control = controls[3]
        else:
            log_message("Not enough controls found.")
            return
    except Exception as e:
        log_message(f"Control selection error: {e}")
        return
    monitor_control(control, main_window)

def main():
    log_message(f"Starting {WINDOW_TITLE} monitor.")
    attempts = 0
    while attempts < MAX_ATTEMPTS:
        pid = find_window_pid()
        if pid:
            monitor_window()
            attempts = 0
        else:
            attempts += 1
            log_message(f"Attempt {attempts}/{MAX_ATTEMPTS}: Window not found.")
        time.sleep(5)
    log_message("Max attempts reached. Exiting monitor.")

if __name__ == "__main__":
    main()
