"""
mt5.py – MetaTrader-5 helper functions (NO Discord code).
"""

from __future__ import annotations

import logging
from datetime import datetime

import MetaTrader5 as mt5


# --------------------------------------------------------------------------- #
# Connection helpers
# --------------------------------------------------------------------------- #

def initialise() -> bool:
    """Initialise connection to a local running MT5 terminal."""
    if mt5.initialize():
        logging.info("Connected to MT5 build %s", mt5.version())
        return True
    logging.error("MT5 init failed: %s", mt5.last_error())
    return False


def _ensure():
    """Ensure we're connected before any data call."""
    if not mt5.initialized():
        if not initialise():
            raise RuntimeError("MT5 not initialised")


# --------------------------------------------------------------------------- #
# Formatting helpers
# --------------------------------------------------------------------------- #

def _fmt(p: float) -> str:           # pretty-print price
    return f"{p:,.5f}"


# --------------------------------------------------------------------------- #
# Core API exposed to the bot / other scripts
# --------------------------------------------------------------------------- #

def get_open_positions() -> list[mt5.TradePosition]:
    _ensure()
    return list(mt5.positions_get() or [])


def get_open_positions_report() -> str:
    """Markdown table of all open positions."""
    pos = get_open_positions()
    if not pos:
        return "*(No open positions)*"

    dt = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
    lines = [
        f"**Open positions** (UTC {dt})",
        "",
        "| Symbol | Type | Lots | Open | P/L |",
        "|--------|------|------:|------:|------:|",
    ]
    total = 0.0
    for p in pos:
        typ = "BUY" if p.type == mt5.ORDER_TYPE_BUY else "SELL"
        pl  = p.profit
        total += pl
        lines.append(f"| {p.symbol} | {typ} | {p.volume:.2f} "
                     f"| {_fmt(p.price_open)} | {pl:,.0f} |")
    lines.append(f"| **TOTAL** |  |  |  | **{total:,.0f}** |")
    return "\n".join(lines)


def get_weighted_positions_report() -> str:
    """Net long/short lots per symbol."""
    pos = get_open_positions()
    if not pos:
        return "*(No open positions)*"

    agg: dict[str, float] = {}
    for p in pos:
        mult = 1 if p.type == mt5.ORDER_TYPE_BUY else -1
        agg[p.symbol] = agg.get(p.symbol, 0) + p.volume * mult

    lines = ["**Net lots**", "",
             "| Symbol | Lots |",
             "|--------|------:|"]
    for sym, lots in sorted(agg.items()):
        lines.append(f"| {sym} | {lots:+.2f} |")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Re-export public names
# --------------------------------------------------------------------------- #

__all__ = [
    "initialise",
    "get_open_positions",
    "get_open_positions_report",
    "get_weighted_positions_report",
]
