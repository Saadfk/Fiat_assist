#!/usr/bin/env python3
# monitors/flylines_to_headlines.py

"""
Monitor headlines from "Breaking News - The Fly" and log new items
to headlines.csv with timestamp format YYYY-MM-DD HH:MM:SS,HeadlineText
"""

import os
import time
import datetime
import csv

import pychrome
from bs4 import BeautifulSoup

try:
    import winsound
    HAVE_WINSOUND = True
except ImportError:
    HAVE_WINSOUND = False

def beep_error():
    if HAVE_WINSOUND:
        for _ in range(3):
            winsound.Beep(1000, 500)
            time.sleep(0.1)
    else:
        print("ERROR: winsound not available.")

def attach_to_tab(browser, target_title="Breaking News - The Fly"):
    tabs = browser.list_tab()
    print(f"Found {len(tabs)} tabs.")
    for tab in tabs:
        try:
            tab.start()
            tab.call_method("Runtime.enable")
            result = tab.call_method("Runtime.evaluate", expression="document.title")
            title = result.get("result", {}).get("value", "")
            if target_title in title:
                print("Found target tab.")
                return tab
            tab.stop()
        except Exception as e:
            print(f"Error with tab ID {tab.id}: {e}")
            try:
                tab.stop()
            except:
                pass
    raise RuntimeError(f"Tab titled '{target_title}' not found.")

def refresh_page(tab):
    tab.call_method("Page.reload", ignoreCache=True)
    time.sleep(4)

def dump_full_html(tab):
    result = tab.call_method(
        "Runtime.evaluate",
        expression="document.documentElement.outerHTML"
    )
    return result.get("result", {}).get("value", "")

def parse_headlines(html_text):
    soup = BeautifulSoup(html_text, "html.parser")
    return [
        link.get_text(strip=True)
        for link in soup.select('a.newsTitleLink')
        if link.get_text(strip=True)
    ]

def load_existing(csv_filename):
    existing = set()
    if os.path.exists(csv_filename):
        with open(csv_filename, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) >= 2:
                    existing.add(row[1])
    return existing

def main():
    # write into headlines.csv in this script's directory
    csv_file = os.path.join(os.path.dirname(__file__), "headlines.csv")

    browser = pychrome.Browser(url="http://127.0.0.1:9222")
    try:
        tab = attach_to_tab(browser, "Breaking News - The Fly")
    except RuntimeError as e:
        print(f"Error: {e}")
        beep_error()
        return

    seen = load_existing(csv_file)
    print(f"Loaded {len(seen)} existing headlines.")

    try:
        while True:
            try:
                refresh_page(tab)
                html_text = dump_full_html(tab)
                headlines = parse_headlines(html_text)
                new_items = [h for h in headlines if h not in seen]

                if new_items:
                    with open(csv_file, "a", newline="", encoding="utf-8") as f:
                        writer = csv.writer(f)
                        for headline in new_items:
                            seen.add(headline)
                            ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            print(f"[{ts}] New headline: {headline}")
                            writer.writerow([ts, headline])

                time.sleep(1)

            except pychrome.exceptions.RuntimeException as re:
                print(f"Runtime error: {re}")
                beep_error()
                time.sleep(5)
                try:
                    tab = attach_to_tab(browser, "Breaking News - The Fly")
                except RuntimeError as e:
                    print(e)
                    beep_error()
                    continue

            except Exception as ex:
                print(f"Unexpected error: {ex}")
                beep_error()
                time.sleep(5)

    except KeyboardInterrupt:
        print("Monitoring stopped.")

    finally:
        try:
            tab.stop()
        except:
            pass

if __name__ == "__main__":
    main()
