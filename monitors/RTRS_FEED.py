#!/usr/bin/env python3
# RTRS_FEED.py  –  Reuters Workspace headline streamer (visible‑row aware)

import csv
import re
import sys
import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple, List

import pythoncom
import comtypes.client
from comtypes.gen import UIAutomationClient as uia_defs
from pywinauto import Desktop
from pywinauto.controls.uiawrapper import UIAWrapper

# ───────────── Config ─────────────
WIN_SUBSTR    = sys.argv[1] if len(sys.argv) > 1 else "FIATFEED"
CONTAINER_AID = "nsw-container"
CSV_PATH      = Path("headlines.csv")
TIME_RE       = re.compile(r"^\d{2}:\d{2}:\d{2}$")      # HH:MM:SS
CACHE_SIZE    = 800
# ──────────────────────────────────

@dataclass
class Candidate:
    idx: int
    ts: str
    headline: str
    top: int
    offscreen: bool

# ─────────── Locate UI elements ───
def locate_container() -> Tuple[UIAWrapper, UIAWrapper]:
    win = next(w for w in Desktop(backend="uia").windows()
               if WIN_SUBSTR.lower() in w.window_text().lower())
    container = next(c for c in win.descendants()
                     if c.element_info.control_type == "Group"
                     and c.element_info.automation_id == CONTAINER_AID)
    return win, container

# ─────────── Scan container ───────
def visible_headline(container: UIAWrapper) -> Optional[Candidate]:
    kids = container.children()
    cands: List[Candidate] = []

    for i, ctrl in enumerate(kids):
        if ctrl.element_info.control_type != "Text":
            continue
        txt = ctrl.window_text().strip()
        if not txt or TIME_RE.fullmatch(txt):
            continue                               # not a headline
        # look backward for timestamp
        ts = ""
        for back in reversed(kids[:i]):
            if back.element_info.control_type == "Text":
                t = back.window_text().strip()
                if TIME_RE.fullmatch(t):
                    ts = t
                    break
        if not ts:
            continue
        cands.append(
            Candidate(i, ts, txt,
                      ctrl.element_info.rectangle.top,
                      not ctrl.is_visible()))  # ← True if off‑screen

    # Prefer visible candidates; among them the smallest Y (closest to top)
    visible = [c for c in cands if not c.offscreen]
    pool = visible or cands                       # fallback: any candidate
    if not pool:
        return None
    return min(pool, key=lambda c: c.top)         # top‑most

# ─────────── Emit / CSV / dedup ───
CSV_PATH.touch(exist_ok=True)
csv_fp = CSV_PATH.open("a", newline="", encoding="utf-8")
csv_writer = csv.writer(csv_fp)
_seen = OrderedDict()

def _stamp(ts: str) -> str:
    """Attach correct date, considering midnight roll‑over."""
    now = datetime.now()
    hh, mm, ss = map(int, ts.split(":"))
    candidate = now.replace(hour=hh, minute=mm, second=ss, microsecond=0)
    if candidate > now:                 # e.g. 23:59 while now is 02:00
        candidate -= timedelta(days=1)
    return candidate.strftime("%Y-%m-%d %H:%M:%S")

def emit(ts: str, headline: str):
    if headline in _seen:
        return
    _seen[headline] = None
    if len(_seen) > CACHE_SIZE:
        _seen.popitem(last=False)

    full_ts = _stamp(ts)
    print(f"{full_ts} | {headline}", flush=True)
    csv_writer.writerow([full_ts, headline, "RTRS"])
    csv_fp.flush()

# ─────────── UIA event handler ────
uia = comtypes.client.CreateObject(uia_defs.CUIAutomation8,
                                   interface=uia_defs.IUIAutomation)

class ContainerHandler(comtypes.COMObject):
    _com_interfaces_ = [uia_defs.IUIAutomationEventHandler]
    def __init__(self, container: UIAWrapper):
        super().__init__()
        self.container = container
    def HandleAutomationEvent(self, sender, event_id):
        cand = visible_headline(self.container)
        if cand:
            emit(cand.ts, cand.headline)

# ─────────── main ─────────────────
def main():
    win, container = locate_container()
    print(f"[+] Window '{win.window_text()}' hwnd={win.handle}")
    print(f"[+] Container aid='{CONTAINER_AID}' rect={container.element_info.rectangle}")

    # Show current visible headline once
    cand = visible_headline(container)
    if cand:
        print(f"[DBG] initial pick child #{cand.idx} rectTop={cand.top} "
              f"offscreen={cand.offscreen}")
        emit(cand.ts, cand.headline)
    else:
        print("[!] No headline detected at start‑up")

    # Subscribe to future changes
    handler = ContainerHandler(container)
    scope = uia_defs.TreeScope_Subtree
    for evt in (uia_defs.UIA_StructureChangedEventId,
                uia_defs.UIA_Text_TextChangedEventId):
        uia.AddAutomationEventHandler(evt, container.element_info.element,
                                      scope, None, handler)

    try:
        while True:
            pythoncom.PumpWaitingMessages()
            time.sleep(0.05)
    finally:
        for evt in (uia_defs.UIA_StructureChangedEventId,
                    uia_defs.UIA_Text_TextChangedEventId):
            uia.RemoveAutomationEventHandler(evt, container.element_info.element,
                                              handler)
        csv_fp.close()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[!] stopped")
    except Exception as e:
        print(f"[ERR] {e}")
