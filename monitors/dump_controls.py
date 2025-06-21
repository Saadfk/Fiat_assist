"""
Enumerate every UI-Automation element under the Reuters/Workspace window
and dump the key properties to both console and CSV.

Run:  python dump_controls.py             # uses default "FIATFEED" title
   or: python dump_controls.py "My Title" # custom window title
"""

import csv
import sys
import time
from pathlib import Path

from pywinauto import Application, Desktop
from pywinauto.controls.uiawrapper import UIAWrapper

WINDOW_TITLE = sys.argv[1] if len(sys.argv) > 1 else "FIATFEED"
OUT_CSV = Path("fiatfeed_controls.csv")


def get_depth(wrap: "UIAWrapper") -> int:
    """Return nesting depth from the main window (root = 0)."""
    d, parent = 0, wrap
    while True:
        try:
            parent = parent.parent()
        except RuntimeError:  # reached the root – UIA throws
            break
        if parent is None:
            break
        d += 1
    return d


def main():
    # locate live window
    try:
        win = next(w for w in Desktop(backend="uia").windows()
                   if WINDOW_TITLE.lower() in w.window_text().lower())
    except StopIteration:
        print(f"[ERR] No window containing '{WINDOW_TITLE}' found.")
        sys.exit(1)

    app = Application(backend="uia").connect(process=win.process_id())
    main_win = app.window(handle=win.handle)
    time.sleep(1)  # let Workspace finish painting

    # walk the tree
    rows = []
    for idx, ctrl in enumerate(main_win.descendants()):
        info = ctrl.element_info
        rows.append({
            "idx": idx,
            "control_type": info.control_type,
            "name": info.name,
            "automation_id": info.automation_id,
            "class_name": info.class_name,
            "rect": f"{info.rectangle}",
            "depth": get_depth(ctrl)  # ← was: ctrl.depth
        })

        print(f"{idx:3} {' ' * get_depth(ctrl) * 2}"
              f"{info.control_type:<18} {info.name or '<no name>'}")

    # save to CSV for offline inspection
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nDumped {len(rows)} controls → {OUT_CSV.resolve()}")


if __name__ == "__main__":
    main()
