from __future__ import annotations

import discord

from modules.config import LOGS_CHANNEL_ENABLED, LOGS_CHANNEL_ID

# Keep the active bot instance in one place for cross-module helpers
_bot = None


def set_bot(bot) -> None:
    # Store the bot instance for later logging and channel lookups
    global _bot
    _bot = bot


def get_bot():
    return _bot


async def log_to_channel(message: str):
    # Fallback to stdout if the log channel is unavailable
    if not LOGS_CHANNEL_ENABLED:
        print(f"[LOG] {message}")
        return

    bot = get_bot()
    if bot is None:
        print(f"[LOG] {message}")
        return

    log_channel = bot.get_channel(LOGS_CHANNEL_ID)
    if log_channel:
        try:
            await safe_send(log_channel, message)
        except Exception as exc:
            print(f"[WARN] Failed to write log message to channel: {exc}")
            print(f"[LOG] {message}")
    else:
        print(f"[LOG] {message}")


async def safe_send(target, *args, **kwargs):
    try:
        return await target.send(*args, **kwargs)
    except discord.Forbidden:
        print(f"[WARN] Missing send permission for channel: {getattr(target, 'id', 'unknown')}")
        return None
    except Exception as exc:
        print(f"[WARN] Failed to send message to channel {getattr(target, 'id', 'unknown')}: {exc}")
        return None
