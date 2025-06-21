import os
import re
import requests
from utils import Keys
from openai import OpenAI
from PyPDF2 import PdfReader

# Configuration flags
ENABLE_DISCORD = True  # Set to False to disable Discord integration entirely
PROMPT_BEFORE_SEND = False  # Set to False to auto-send without prompting after summary
DISCORD_CHANNEL_ID = "1176530579433455688"
DISCORD_API_URL = f"https://discord.com/api/v9/channels/{DISCORD_CHANNEL_ID}/messages"

# OpenAI client setup
api_key = os.environ.get("OPENAI_API_KEY", Keys.OPENAI_API)
client = OpenAI(api_key=api_key)

# Directory to monitor for PDFs
MONITOR_DIR = r"C:\Users\User\Dropbox\Current\2025"


def send_to_discord(title: str, summary: str) -> None:
    """
    Send the given summary to Discord using a bot. Title will be formatted as a markdown heading.
    """
    token = Keys.DISCORD_BOT_TOKEN
    headers = {
        "Authorization": f"Bot {token}",
        "Content-Type": "application/json"
    }
    content = f"# {title}\n{summary}"
    payload = {"content": content}
    response = requests.post(DISCORD_API_URL, json=payload, headers=headers)
    if not response.ok:
        print(f"Failed to send to Discord: {response.status_code} {response.text}")


def list_recent_files(directory, count=50):
    all_files = []
    for root, _, files in os.walk(directory):
        for fname in files:
            all_files.append(os.path.join(root, fname))
    all_files.sort(key=lambda f: os.path.getctime(f), reverse=True)
    recent_files = all_files[:count]
    print("\nRecent files:")
    for idx, file_path in enumerate(recent_files):
        name = os.path.splitext(os.path.basename(file_path))[0]
        print(f"  {idx}: {name}")
    return recent_files


def extract_text_from_pdf(file_path):
    text = ""
    try:
        reader = PdfReader(file_path)
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text
    except Exception as e:
        print(f"Error extracting text: {e}")
    return text


def process_file(selected_file):
    file_name = os.path.splitext(os.path.basename(selected_file))[0]
    print(f"\nExtracting text from: {file_name}")
    text_content = extract_text_from_pdf(selected_file)
    if not text_content.strip():
        print("No extractable text found.")
        return

    prompt_message = (
        "Summarize in bullet points very succinctly, focusing on direct opinions:\n"
        + text_content
    )
    messages = [
        {"role": "system", "content": "You are a hedge fund analyst"},
        {"role": "user", "content": prompt_message}
    ]

    print("Sending to OpenAI API for summarization...")
    try:
        completion = client.chat.completions.create(model="o3-mini", messages=messages)
        summary = completion.choices[0].message.content.strip()
    except Exception as e:
        print(f"API request failed: {e}")
        return

    # Display summary on console
    print(f"\n### {file_name} ###")
    print(summary)
    print("\n" + "#" * 50 + "\n")

    # Handle Discord sending
    if ENABLE_DISCORD:
        send_it = True
        if PROMPT_BEFORE_SEND:
            while True:
                confirm = input(f"Send summary of '{file_name}' to Discord? (y/n): ").strip().lower()
                if confirm in ('y', 'n'):
                    send_it = (confirm == 'y')
                    break
                print("Please enter 'y' or 'n'.")
        if send_it:
            print(f"Sending to Discord channel {DISCORD_CHANNEL_ID}...")
            send_to_discord(file_name, summary)
            print("Sent.")


def search_files(keyword, files):
    matches = []
    for idx, path in enumerate(files):
        name = os.path.splitext(os.path.basename(path))[0]
        if keyword.lower() in name.lower():
            matches.append((idx, path))
    return matches


def main():
    print(f"Monitoring directory: {MONITOR_DIR}")
    print("Commands:")
    print("  'r'               - List recent files")
    print("  <ID> or IDs      - Summarize file(s), e.g. '1' or '1,2,4'")
    print("  s \"keyword\"      - Search files by keyword")
    print("  l <number>        - Show full path of entry in last search")
    print("  'q'               - Quit")

    recent_files = []
    current_ordered = []

    while True:
        cmd = input("\nEnter command: ").strip()
        if cmd.lower() == 'q':
            print("Exiting.")
            break
        elif cmd.lower() == 'r':
            recent_files = list_recent_files(MONITOR_DIR, count=40)
            current_ordered = []
        elif cmd.lower().startswith('s '):
            match = re.match(r'^s\s+\"(.+?)\"$', cmd)
            if match:
                keyword = match.group(1)
                if not recent_files:
                    recent_files = list_recent_files(MONITOR_DIR, count=40)
                res = search_files(keyword, recent_files)
                if res:
                    current_ordered = [path for _, path in res]
                    print(f"Ordered list for '{keyword}':")
                    for i, path in enumerate(current_ordered):
                        print(f"  {i}: {os.path.splitext(os.path.basename(path))[0]}")
                else:
                    print(f"No files matching '{keyword}'.")
                    current_ordered = []
            else:
                print("Invalid search. Use: s \"keyword\"")
        elif cmd.lower().startswith('l '):
            match = re.match(r'^l\s+(\d+)$', cmd)
            if match:
                idx = int(match.group(1))
                source = current_ordered or recent_files
                if 0 <= idx < len(source):
                    print(f"Local path: {source[idx]}")
                else:
                    print("Invalid index.")
            else:
                print("Invalid format. Use: l <number>")
        else:
            if not recent_files:
                print("No files listed. Use 'r' to refresh.")
                continue
            ids = [s.strip() for s in cmd.split(',')]
            for s in ids:
                try:
                    i = int(s)
                except ValueError:
                    print(f"Invalid ID: {s}")
                    continue
                if i < 0 or i >= len(recent_files):
                    print(f"ID out of range: {i}")
                    continue
                path = recent_files[i]
                if not path.lower().endswith('.pdf'):
                    print("Unsupported file type.")
                    continue
                process_file(path)


if __name__ == "__main__":
    main()