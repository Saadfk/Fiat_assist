"""discord_trading_bot.py
================================================
A streamlined Discord trading bot that:

1. Mirrors **all** messages (including attachments) from source channel `1369841053649207347` to target channel `855359994547011604` as a red-tinged embed quotation.
2. Provides a single user command:
   * `!positions [t] [\"extra\"]` – report open MT5 positions (optionally tweet when `t` flag supplied).

External project modules required
--------------------------------
- `publishers.publisher.post_to_twitter`
- `RISKCODE.riskmgr.get_open_positions_weight`
- `utils.Keys` (expects `DISCORD_BOT_TOKEN`)
- `utils.myfxbook` helpers

Python deps: `discord.py`, `MetaTrader5`, `pandas`, `numpy`, `pytz`
"""

from __future__ import annotations

import io
import logging
import datetime as dt
from typing import Optional

import discord
from discord.ext import commands
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import pytz

from publishers.publisher import post_to_twitter
from utils import Keys
from utils.myfxbook import get_trading_periods_table, get_gain_by_flag
from RISKCODE.riskmgr import get_open_positions_weight

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
LOGGER = logging.getLogger("DiscordTradingBot")

DISCORD_TOKEN: str = Keys.DISCORD_BOT_TOKEN
MYFXBOOK_URL: str = (
    "https://www.myfxbook.com/members/fiatelpis2/fiatelpis-central-iv-fusion/10569665"
)
DEFAULT_SYMBOL: str = "EURUSD"
DATE_FMT: str = "%Y-%m-%d %H:%M:%S %Z"

# Channel mirroring
SOURCE_CH_ID = 1369841053649207347  # incoming channel
TARGET_CH_ID = 855359994547011604  # destination channel

# ---------------------------------------------------------------------------
# Discord bot setup
# ---------------------------------------------------------------------------

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_last_trading_day(ts: dt.datetime) -> dt.datetime:
    """Return 23:00 UTC of the latest weekday on or before ts."""
    if ts.hour < 23:
        ts -= dt.timedelta(days=1)
    while ts.weekday() > 4:
        ts -= dt.timedelta(days=1)
    return ts.replace(hour=23, minute=0, second=0, microsecond=0)


def fetch_server_time(symbol: str = DEFAULT_SYMBOL) -> dt.datetime:
    """Get MT5 server time via a symbol tick."""
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        raise RuntimeError(f"Failed to retrieve tick for symbol {symbol}")
    return dt.datetime.fromtimestamp(tick.time, pytz.utc)

# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

@bot.event
async def on_ready() -> None:
    LOGGER.info("Bot connected as %s (id=%s)", bot.user, bot.user.id)


@bot.event
async def on_message(message: discord.Message) -> None:
    """Mirror messages as a red embed quotation, then process commands."""
    if message.author == bot.user:
        return

    if message.channel.id == SOURCE_CH_ID:
        dest = bot.get_channel(TARGET_CH_ID)
        if dest:
            # Prepare attachments
            files: list[discord.File] = []
            for att in message.attachments:
                data = await att.read()
                files.append(discord.File(io.BytesIO(data), filename=att.filename))
            # Create a red-colored embed quote
            embed = discord.Embed(
                description=message.content or "",
                color=discord.Color.red()
            )
            await dest.send(embed=embed, files=files)
        else:
            LOGGER.warning("Target channel %s not found", TARGET_CH_ID)

    # Allow other commands like !positions
    await bot.process_commands(message)

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@bot.command(name="positions")
async def positions_cmd(
    ctx: commands.Context,
    flag: Optional[str] = None,
    *,
    extra: Optional[str] = None,
) -> None:
    """Report open positions; tweet if flag 't' is given."""
    try:
        positions_df = get_open_positions_weight()
        mt5_positions = mt5.positions_get()

        # No open positions
        if not mt5_positions:
            closed_pnl = get_gain_by_flag(
                "Today", get_trading_periods_table(MYFXBOOK_URL)
            )
            now = fetch_server_time()
            await ctx.send(
                f"Timestamp: {now.strftime(DATE_FMT)}\n"
                f"**No open positions.**\n"
                f"P&L (Today): {closed_pnl}"
            )
            return
            positions_df = get_open_positions_weight()
            mt5_positions = mt5.positions_get() or []  # normalize to empty list
        # Build and merge DataFrames
        df_mt5 = (
            pd.DataFrame([p._asdict() for p in mt5_positions])  # type: ignore
            [["symbol", "price_open", "profit", "time"]]
            .astype({"price_open": float, "profit": float})
        )
        merged = pd.merge(
            positions_df, df_mt5, on="time", how="left"
        ).drop_duplicates(subset=["symbol_x", "price_open", "profit"])
        merged["weight_numeric"] = (
            merged["weight_formatted"].str.rstrip("%").astype(float)
        )

        # Aggregate by symbol
        grouped = (
            merged.groupby("symbol_x").apply(
                lambda g: pd.Series({
                    "weight_numeric": g["weight_numeric"].sum(),
                    "price_open": np.average(
                        g["price_open"], weights=g["weight_numeric"]
                    ),
                    "profit": g["profit"].sum(),
                })
            )
            .reset_index()
        )
        grouped["weight_formatted"] = grouped["weight_numeric"].map(
            lambda x: f"{x:.0f}%"
        )

        # Calculate metrics
        server_time = fetch_server_time(grouped.iloc[0]["symbol_x"])
        session_start = get_last_trading_day(server_time)
        closed_pnl = get_gain_by_flag(
            "Today", get_trading_periods_table(MYFXBOOK_URL)
        )
        open_pnl = grouped["profit"].sum()
        gross_lev = grouped["weight_numeric"].abs().sum() / 100

        # Build message lines
        discord_lines: list[str] = []
        twitter_lines: list[str] = []
        for _, row in grouped.iterrows():
            emoji = "🟢" if row["weight_numeric"] > 0 else "🔴"
            pnl_em = "🟢" if row["profit"] > 0 else "🔴"
            discord_lines.append(
                f"{row['symbol_x']}: Wgt {row['weight_formatted']}, "
                f"Open {row['price_open']:.2f}, P&L {pnl_em} {row['profit']:.0f} bps"
            )
            twitter_lines.append(
                f"{emoji} ${row['symbol_x']}: Wgt {row['weight_formatted']}, "
                f"Price {row['price_open']:.2f}, p&l {row['profit']:.0f} bps"
            )

        margin_str = f"Gross leverage: {gross_lev:.1f} x"
        time_str = f"Timestamp: {server_time.strftime(DATE_FMT)}"

        # Discord message
        discord_msg = (
            f"{time_str}\n**Open Positions and Weights:**\n```\n"
            + "\n".join(discord_lines)
            + f"\n{margin_str}\n"
            + f"Closed PnL (since {session_start.strftime(DATE_FMT)}): {closed_pnl}\n"
            + f"Open PnL: {open_pnl:.0f} bps\n```"
        )

        # Twitter output if requested
        if flag and flag.lower() == "t":
            extra_clean = extra.strip('"') if extra else ""
            header = f"**{extra_clean}**\n" if extra_clean else ""
            twitter_msg = (
                header + "===\n" + "\n".join(twitter_lines) +
                f"\n===\n{margin_str}\nClosed p&l: {closed_pnl}\n"
                + f"Open p&l: {open_pnl:.0f} bps"
            )
            post_to_twitter(twitter_msg)
            await ctx.send("Positions have been posted to Twitter.")
        else:
            await ctx.send(discord_msg)

    except Exception as e:
        await ctx.send(f"Error fetching positions: {e}")
    finally:
        mt5.shutdown()

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
