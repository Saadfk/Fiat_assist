#!/usr/bin/env python3
# RTRS_FEED.py  –  Reuters Workspace live-headline streamer (July 2025)

import csv, re, sys, time, winsound, traceback, pythoncom
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Optional, Tuple

import comtypes.client
from comtypes.gen import UIAutomationClient as uia_defs
from pywinauto import Desktop
from pywinauto.controls.uiawrapper import UIAWrapper

# ─── Config ────────────────────────────────────────────────────────────────
WIN_SUBSTR = sys.argv[1] if len(sys.argv) > 1 else "FIATFEED"
DOC_NAME   = "NEWS2.0"            # name shown in UIA for the feed Document
CSV_PATH   = Path("headlines.csv")
TIME_RE    = re.compile(r"^\d{2}:\d{2}:\d{2}$")   # HH:MM:SS
CACHE_SIZE = 800
# ───────────────────────────────────────────────────────────────────────────

@dataclass
class Candidate:
    idx: int
    ts: str
    headline: str
    top: int
    offscreen: bool

# ─── Locate Reuters window + feed container ───────────────────────────────
def locate_container(retries: int = 20, delay: float = 0.5
                     ) -> Tuple[UIAWrapper, UIAWrapper]:
    for _ in range(retries):
        try:
            win = next(w for w in Desktop(backend="uia").windows()
                       if WIN_SUBSTR.lower() in w.window_text().lower())

            doc = next(d for d in win.descendants()
                       if d.element_info.control_type == "Document"
                       and d.element_info.name == DOC_NAME)

            return win, doc.parent()   # the row container
        except StopIteration:
            time.sleep(delay)
    raise RuntimeError(f"Window '{WIN_SUBSTR}' or Document '{DOC_NAME}' not found")

# ─── Extract visible headline ─────────────────────────────────────────────
def visible_headline(container: UIAWrapper) -> Optional[Candidate]:
    text_nodes: List[UIAWrapper] = list(container.descendants(control_type="Text"))
    print(f"[DBG] saw {len(text_nodes)} Text nodes on first scan")  # only prints once

    cands: List[Candidate] = []
    for i, ctrl in enumerate(text_nodes):
        txt = ctrl.window_text().strip()
        if not txt or TIME_RE.fullmatch(txt):
            continue

        # find timestamp backwards from current node
        ts = next((back.window_text().strip()
                  for back in reversed(text_nodes[:i])
                  if TIME_RE.fullmatch(back.window_text().strip())), "")
        if not ts:
            continue

        cands.append(Candidate(i, ts, txt,
                               ctrl.element_info.rectangle.top,
                               not ctrl.is_visible()))

    if not cands:
        return None
    onscreen = [c for c in cands if not c.offscreen]
    return min(onscreen or cands, key=lambda c: c.top)

# ─── CSV / dedup / beep ───────────────────────────────────────────────────
CSV_PATH.touch(exist_ok=True)
csv_fp = CSV_PATH.open("a", newline="", encoding="utf-8")
csv_writer = csv.writer(csv_fp)
_seen = OrderedDict()

def _normalize_ts(ts: str) -> str:
    now = datetime.now()
    h, m, s = map(int, ts.split(":"))
    dt = now.replace(hour=h, minute=m, second=s, microsecond=0)
    if dt > now:
        dt -= timedelta(days=1)
    return dt.strftime("%Y-%m-%d %H:%M:%S")

def emit(ts: str, headline: str):
    if headline in _seen:
        return
    _seen[headline] = None
    if len(_seen) > CACHE_SIZE:
        _seen.popitem(last=False)

    full_ts = _normalize_ts(ts)
    print(f"{full_ts} | {headline}", flush=True)
    csv_writer.writerow([full_ts, headline, "RTRS"]); csv_fp.flush()

    try:
        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
    except RuntimeError:
        winsound.Beep(1500, 400)

# ─── Event handler ────────────────────────────────────────────────────────
uia = comtypes.client.CreateObject(uia_defs.CUIAutomation8,
                                   interface=uia_defs.IUIAutomation)

class FeedHandler(comtypes.COMObject):
    _com_interfaces_ = [uia_defs.IUIAutomationEventHandler]
    def __init__(self, box: UIAWrapper):
        super().__init__(); self.box = box
    def HandleAutomationEvent(self, *_):
        cand = visible_headline(self.box)
        if cand:
            emit(cand.ts, cand.headline)

# ─── Main loop ────────────────────────────────────────────────────────────
def main():
    win, container = locate_container()
    print(f"[+] Window '{win.window_text()}'  hwnd={win.handle}")
    print(f"[+] Container rect={container.element_info.rectangle}")

    # print current headline once
    cand = visible_headline(container)
    if cand:
        emit(cand.ts, cand.headline)
    else:
        print("[!] No headline visible yet – waiting for events")

    handler = FeedHandler(container)
    for eid in (uia_defs.UIA_StructureChangedEventId,
                uia_defs.UIA_Text_TextChangedEventId):
        uia.AddAutomationEventHandler(eid, container.element_info.element,
                                      uia_defs.TreeScope_Subtree, None, handler)

    try:
        while True:
            pythoncom.PumpWaitingMessages(); time.sleep(0.05)
    finally:
        for eid in (uia_defs.UIA_StructureChangedEventId,
                    uia_defs.UIA_Text_TextChangedEventId):
            uia.RemoveAutomationEventHandler(eid, container.element_info.element,
                                              handler)
        csv_fp.close()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[!] stopped by user")
    except Exception as e:
        print(f"[ERR] {type(e).__name__}: {e or '<empty>'}")
        traceback.print_exc()
