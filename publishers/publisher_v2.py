#!/usr/bin/env python3
# RTRS_FEED.py  –  Reuters Workspace live-headline streamer + Discord push

import csv, re, sys, time, traceback, winsound, pythoncom, requests
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Tuple

from utils.Keys import DISCORD_BOT_TOKEN          # your token
import comtypes.client
from comtypes.gen import UIAutomationClient as uia_defs
from pywinauto import Desktop
from pywinauto.controls.uiawrapper import UIAWrapper

# ─── USER SETTINGS ────────────────────────────────────────────────────────
WIN_SUBSTR          = sys.argv[1] if len(sys.argv) > 1 else "FIATFEED"
DOC_NAME            = "NEWS2.0"
CSV_PATH            = Path("headlines.csv")
DISCORD_CHANNEL_ID  = "855359994547011604"        # <-- put your channel ID here
CACHE_SIZE          = 800
TIME_RE             = re.compile(r"^\d{2}:\d{2}:\d{2}$")   # HH:MM:SS
EMBED_COLOUR        = 0xFFA500                      # orange
# ───────────────────────────────────────────────────────────────────────────

# ─── Discord helper ───────────────────────────────────────────────────────
def post_to_discord(channel_id: str, content: str):
    url = f"https://discord.com/api/channels/{channel_id}/messages"
    headers = {
        "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
        "Content-Type": "application/json"
    }
    embed = {"description": content, "color": EMBED_COLOUR}
    resp = requests.post(url, headers=headers, json={"embeds": [embed]})
    if resp.status_code not in (200, 201):
        print(f"Discord error {resp.status_code}: {resp.text}", flush=True)

# ─── UI-Automation plumbing (unchanged logic) ─────────────────────────────
@dataclass
class Candidate:
    idx: int; ts: str; headline: str; top: int; offscreen: bool

def locate_container(retries: int = 20, delay: float = .5
                     ) -> Tuple[UIAWrapper, UIAWrapper]:
    for _ in range(retries):
        try:
            win = next(w for w in Desktop(backend="uia").windows()
                       if WIN_SUBSTR.lower() in w.window_text().lower())
            doc = next(d for d in win.descendants()
                       if d.element_info.control_type == "Document"
                       and d.element_info.name == DOC_NAME)
            return win, doc.parent()
        except StopIteration:
            time.sleep(delay)
    raise RuntimeError(f"Window '{WIN_SUBSTR}' or Document '{DOC_NAME}' not found")

def visible_headline(container: UIAWrapper) -> Optional[Candidate]:
    nodes: List[UIAWrapper] = list(container.descendants(control_type="Text"))
    cands: List[Candidate] = []
    for i, ctrl in enumerate(nodes):
        txt = ctrl.window_text().strip()
        if not txt or TIME_RE.fullmatch(txt):
            continue
        ts = next((b.window_text().strip()
                  for b in reversed(nodes[:i])
                  if TIME_RE.fullmatch(b.window_text().strip())), "")
        if not ts:
            continue
        cands.append(Candidate(i, ts, txt,
                               ctrl.element_info.rectangle.top,
                               not ctrl.is_visible()))
    if not cands:
        return None
    onscreen = [c for c in cands if not c.offscreen]
    return min(onscreen or cands, key=lambda c: c.top)

# ─── CSV / dedup / alert / Discord ────────────────────────────────────────
CSV_PATH.touch(exist_ok=True)
csv_out = CSV_PATH.open("a", newline="", encoding="utf-8")
csv_writer = csv.writer(csv_out)
_seen = OrderedDict()

def to_full_ts(raw: str) -> str:
    now = datetime.now()
    h, m, s = map(int, raw.split(":"))
    ts = now.replace(hour=h, minute=m, second=s, microsecond=0)
    if ts > now:
        ts -= timedelta(days=1)
    return ts.strftime("%Y-%m-%d %H:%M:%S"), ts.strftime("%H:%M")

def emit(ts_raw: str, headline: str):
    if headline in _seen:                           # dedup
        return
    _seen[headline] = None
    if len(_seen) > CACHE_SIZE:
        _seen.popitem(last=False)

    full_ts, hhmm = to_full_ts(ts_raw)
    print(f"{full_ts} | {headline}", flush=True)
    csv_writer.writerow([full_ts, headline, "RTRS"]); csv_out.flush()

    # beep
    winsound.Beep(2000, 500)

    # Discord
    post_to_discord(DISCORD_CHANNEL_ID, f"**{hhmm} | {headline}**")

# ─── UIA event glue ───────────────────────────────────────────────────────
uia = comtypes.client.CreateObject(uia_defs.CUIAutomation8,
                                   interface=uia_defs.IUIAutomation)

class Handler(comtypes.COMObject):
    _com_interfaces_ = [uia_defs.IUIAutomationEventHandler]
    def __init__(self, box): super().__init__(); self.box = box
    def HandleAutomationEvent(self, *_):
        cand = visible_headline(self.box)
        if cand: emit(cand.ts, cand.headline)

# ─── Main loop ────────────────────────────────────────────────────────────
def main():
    win, container = locate_container()
    print(f"[+] Window '{win.window_text()}'  hwnd={win.handle}")

    first = visible_headline(container)
    if first:
        emit(first.ts, first.headline)
    else:
        print("[!] Waiting for first headline…")

    h = Handler(container)
    for eid in (uia_defs.UIA_StructureChangedEventId,
                uia_defs.UIA_Text_TextChangedEventId):
        uia.AddAutomationEventHandler(eid, container.element_info.element,
                                      uia_defs.TreeScope_Subtree, None, h)

    try:
        while True:
            pythoncom.PumpWaitingMessages(); time.sleep(.05)
    finally:
        for eid in (uia_defs.UIA_StructureChangedEventId,
                    uia_defs.UIA_Text_TextChangedEventId):
            uia.RemoveAutomationEventHandler(eid, container.element_info.element, h)
        csv_out.close()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[!] stopped")
    except Exception as exc:
        print(f"[ERR] {type(exc).__name__}: {exc}"); traceback.print_exc()
