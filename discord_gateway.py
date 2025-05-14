"""
discord_gateway.py  – the one-and-only Discord connection for Fiat_assist.

Launch this in its own console:

    python discord_gateway.py
"""

import os
import asyncio
import logging

import discord
from discord.ext import commands

from utils import Keys                 # adjust if your secrets helper lives elsewhere
import mt5                             # pure-MT5 utilities (see mt5.py)
from typing import Optional  # already added with the other imports
# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

TOKEN = os.getenv("DISCORD_BOT_TOKEN", getattr(Keys, "DISCORD_BOT_TOKEN", None))
if not TOKEN:
    raise RuntimeError("DISCORD_BOT_TOKEN missing – set env var or utils.Keys")

intents = discord.Intents.default()
intents.message_content = True               # needed if you want to read message text

bot = commands.Bot(command_prefix="!", intents=intents)
_ready = asyncio.Event()                     # signals when the bot is logged in


# --------------------------------------------------------------------------- #
# Events
# --------------------------------------------------------------------------- #

@bot.event
async def on_ready():
    logging.info("Gateway logged in as %s (ID %s)", bot.user, bot.user.id)
    _ready.set()


# --------------------------------------------------------------------------- #
# Public helper – thread-safe “fire-and-forget” send
# --------------------------------------------------------------------------- #

def send_message(channel_id: int,
                 content: Optional[str] = None,
                 embed: Optional[discord.Embed] = None):
    """Send a message via the single bot from *any* sync or async context."""
    async def _send():
        await _ready.wait()                            # wait until login completes
        channel = bot.get_channel(channel_id)          # try cache
        if channel is None:
            channel = await bot.fetch_channel(channel_id)  # fallback API call
        await channel.send(content=content, embed=embed)

    # run the coroutine on the bot’s event-loop
    return asyncio.run_coroutine_threadsafe(_send(), bot.loop)


# --------------------------------------------------------------------------- #
# Bot commands (extend here as needed)
# --------------------------------------------------------------------------- #

@bot.command(name="positions")
async def positions(ctx):
    """`!positions` – show current MT5 open positions."""
    report = mt5.get_open_positions_report()
    await ctx.send(report)


@bot.command(name="weighted")
async def weighted(ctx):
    """`!weighted` – net long/short lots by symbol."""
    summary = mt5.get_weighted_positions_report()
    await ctx.send(summary)


# --------------------------------------------------------------------------- #
# Main entry-point
# --------------------------------------------------------------------------- #

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
    )
    mt5.initialise()          # optional: connect so first command is instant
    bot.run(TOKEN)


if __name__ == "__main__":
    main()
