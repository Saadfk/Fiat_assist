import os
import re
from utils import Keys
from openai import OpenAI
from PyPDF2 import PdfReader

api_key = os.environ.get("OPENAI_API_KEY", Keys.OPENAI_API)
client = OpenAI(api_key=api_key)
MONITOR_DIR = r"C:\Users\User\Dropbox\Current\2025"


def list_recent_files(directory, count=20):
    all_files = []
    for root, _, files in os.walk(directory):
        for fname in files:
            all_files.append(os.path.join(root, fname))
    all_files.sort(key=lambda f: os.path.getctime(f), reverse=True)
    recent_files = all_files[:count]
    print("\nRecent files:")
    for idx, file_path in enumerate(recent_files):
        # Display only the file name without path and extension
        file_name = os.path.splitext(os.path.basename(file_path))[0]
        print(f"  {idx}: {file_name}")
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
    # Get the file name without extension for presentation purposes
    file_name = os.path.splitext(os.path.basename(selected_file))[0]
    print(f"\nExtracting text from: {file_name}")
    text_content = extract_text_from_pdf(selected_file)
    if not text_content.strip():
        print("No extractable text found.")
        return
    prompt_message = "Summarize in bullet points very succinctly, focusing on direct opinions:\n" + text_content
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
    print(f"\n### {file_name} ###")
    print(summary)
    print("\n" + "#" * 50 + "\n")


def search_files(keyword, files):
    """Return a list of tuples (original_index, file_path) for files whose names contain the keyword."""
    matching_files = []
    for idx, file_path in enumerate(files):
        file_name = os.path.splitext(os.path.basename(file_path))[0]
        if keyword.lower() in file_name.lower():
            matching_files.append((idx, file_path))
    return matching_files


def main():
    print(f"Monitoring directory: {MONITOR_DIR}")
    print("Commands:")
    print("  'r'               - List recent files")
    print("  <ID> or comma-separated IDs (e.g., 1 or 1,2,4) - Summarize file(s)")
    print("  s \"keyword\"      - Search recent files for 'keyword' and print an ordered list")
    print("  l <number>        - Show the local path of the file at the given index in the ordered list")
    print("  'q'               - Quit")

    recent_files = []
    # current_ordered_list holds the ordered results from the last search
    current_ordered_list = []

    while True:
        command = input("\nEnter command: ").strip()
        if command.lower() == 'q':
            print("Exiting.")
            break
        elif command.lower() == 'r':
            try:
                recent_files = list_recent_files(MONITOR_DIR, count=40)
                # Clear any previous ordered list when listing all files
                current_ordered_list = []
                if not recent_files:
                    print("No files found.")
            except Exception as e:
                print(f"Error: {e}")
        elif command.lower().startswith('s '):
            # Expecting the format: s "keyword"
            match = re.match(r'^s\s+"(.+)"$', command)
            if match:
                keyword = match.group(1)
                # Ensure we have the recent file list loaded
                if not recent_files:
                    try:
                        recent_files = list_recent_files(MONITOR_DIR, count=40)
                    except Exception as e:
                        print(f"Error: {e}")
                        continue
                results = search_files(keyword, recent_files)
                if results:
                    # Create a new ordered list with re-indexing starting at 0
                    current_ordered_list = [file_path for _, file_path in results]
                    print(f"Ordered list for keyword '{keyword}':")
                    for new_idx, file_path in enumerate(current_ordered_list):
                        file_name = os.path.splitext(os.path.basename(file_path))[0]
                        print(f"  {new_idx}: {file_name}")
                else:
                    print(f"No files found matching '{keyword}'.")
                    current_ordered_list = []
            else:
                print("Invalid search format. Please use: s \"keyword\"")
        elif command.lower().startswith('l '):
            # Expecting the format: l <number>
            match = re.match(r'^l\s+(\d+)$', command)
            if match:
                file_index = int(match.group(1))
                # Prefer the current ordered list if available
                if current_ordered_list:
                    if 0 <= file_index < len(current_ordered_list):
                        selected_path = current_ordered_list[file_index]
                        print(f"Local path: {selected_path}")
                    else:
                        print("Invalid file index for the current ordered list.")
                elif recent_files:
                    # Fallback: use the recent files list if no ordered list exists
                    if 0 <= file_index < len(recent_files):
                        selected_path = recent_files[file_index]
                        print(f"Local path: {selected_path}")
                    else:
                        print("Invalid file index in recent files.")
                else:
                    print("No list available. Please perform a search or refresh the file list first.")
            else:
                print("Invalid format. Use: l <number>")
        else:
            # Assume input is a comma-separated list of file IDs to process
            if not recent_files:
                print("No files listed. Press 'r' to refresh.")
                continue

            indices = [s.strip() for s in command.split(',')]
            for idx_str in indices:
                try:
                    file_index = int(idx_str)
                except ValueError:
                    print(f"Invalid input: {idx_str}")
                    continue
                if file_index < 0 or file_index >= len(recent_files):
                    print(f"Invalid file ID: {file_index}")
                    continue
                selected_file = recent_files[file_index]
                if not os.path.isfile(selected_file):
                    print("File not found.")
                    continue
                # Check for valid file type (e.g., PDF)
                if not selected_file.lower().endswith(".pdf"):
                    print("Not a valid file. Please choose a supported file.")
                    continue
                process_file(selected_file)


if __name__ == "__main__":
    main()
