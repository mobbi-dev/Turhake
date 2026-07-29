#
#
#   ████████╗██╗   ██╗██████╗ ██╗  ██╗ █████╗ ██╗  ██╗███████╗
#   ╚══██╔══╝██║   ██║██╔══██╗██║  ██║██╔══██╗██║ ██╔╝██╔════╝
#      ██║   ██║   ██║██████╔╝███████║███████║█████╔╝ █████╗
#      ██║   ██║   ██║██╔══██╗██╔══██║██╔══██║██╔═██╗ ██╔══╝
#      ██║   ╚██████╔╝██║  ██║██║  ██║██║  ██║██║  ██╗███████╗
#      ╚═╝    ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝
#
#                   Proudly useless Discord bot
#                          ╰─ v0.4.3 ─╯



import os
import json
from pathlib import Path

import discord
from discord.ext import commands
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"
ENV_EXAMPLE_FILE = BASE_DIR / ".env.example"


def _ensure_env_file():
    # Fail fast if the user forgot to create .env
    if ENV_FILE.is_file():
        return

    if ENV_EXAMPLE_FILE.is_file():
        print("ERROR: .env file is missing. Copy .env.example to .env and fill in your values.", flush=True)
    else:
        print("ERROR: .env file is missing and .env.example was not found.", flush=True)
    raise SystemExit(1)

# Load env vars before importing anything that reads them
_ensure_env_file()
load_dotenv(ENV_FILE)

from modules.config import (
    CACHE_DIR,
)
from modules.common import log_to_channel, safe_send, set_bot as set_shared_bot
from modules.common.errors import format_command_error


TOKEN = os.getenv("DISCORD_BOT_TOKEN", "").strip()
if not TOKEN:
    raise ValueError("DISCORD_BOT_TOKEN is missing")


STARTUP_STATE_FILE = CACHE_DIR / "bot_startup_state.json"


intents = discord.Intents.default()
intents.message_content = True


def _load_startup_state():
    if not STARTUP_STATE_FILE.is_file():
        return {"start_count": 0}

    try:
        state = json.loads(STARTUP_STATE_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"WARNING: could not read startup state file: {e}")
        return {"start_count": 0}

    if not isinstance(state, dict):
        return {"start_count": 0}

    state.setdefault("start_count", 0)
    return state


def _save_startup_state(state):
    # Persist the startup counter in the shared cache folder
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    STARTUP_STATE_FILE.write_text(
        json.dumps(state, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


class TurhakeBot(commands.Bot):
    async def setup_hook(self):
        # Load all extensions before connecting to Discord
        await self.load_extension("modules.freegames.freegames")
        await self.load_extension("modules.cs2_updates")
        await self.load_extension("modules.hltv.ranking")
        await self.load_extension("modules.hltv.team_admin")
        await self.load_extension("modules.hltv.monitor")
        await self.load_extension("modules.commands.weather")
        await self.load_extension("modules.commands.cs")
        await self.load_extension("modules.commands.steam")
        await self.load_extension("modules.commands.faceit")
        await self.load_extension("modules.commands.live")
        await self.load_extension("modules.commands.help")


async def _send_startup_report():
    try:
        state = _load_startup_state()
        state["start_count"] = int(state.get("start_count", 0)) + 1
        _save_startup_state(state)

        await log_to_channel(f"🔄 Bot started/restarted #{state['start_count']}")
    except Exception as e:
        print(f"ERROR in startup report: {e}")


bot = TurhakeBot(command_prefix="!", intents=intents)
set_shared_bot(bot)


@bot.event
async def on_ready():
    # Guard against duplicate reports if Discord reconnects
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name="!commands"))
    if not getattr(bot, "_startup_report_sent", False):
        bot._startup_report_sent = True
        await _send_startup_report()


@bot.event
async def on_command_error(ctx, error):
    message = format_command_error(error)
    if message is not None:
        await safe_send(ctx, message)
    else:
        await safe_send(ctx, "😬 An error occurred while running the command")
        raise error


bot.run(TOKEN)
