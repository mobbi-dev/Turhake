import asyncio

import discord
from discord.ext import commands

from modules.config import MATCH_ANNOUNCE_CHANNEL_ID
from modules.hltv.live import get_live_match_selenium
from modules.common import get_bot, safe_send


class LiveCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="live")
    async def live(self, ctx, *, team: str):
        await safe_send(ctx, f"🔍 Searching for a live match for **{team}**...")

        loop = asyncio.get_running_loop()
        # Offload the blocking Selenium call to a worker thread
        match = await loop.run_in_executor(None, get_live_match_selenium, team)

        if not match:
            await safe_send(ctx, "❌ No live match was found or HLTV is not responding.")
            return

        embed = discord.Embed(
            title=f"🔴 LIVE: {match['team1']} vs {match['team2']}",
            url=match['link'],
            description=f"**Score:** {match['score1']} - {match['score2']}",
            color=discord.Color.red()
        )

        bot = get_bot()
        channel = bot.get_channel(MATCH_ANNOUNCE_CHANNEL_ID) if bot else None
        if channel:
            await safe_send(channel, embed=embed)
            await safe_send(ctx, f"✅ Live match found, info posted to <#{MATCH_ANNOUNCE_CHANNEL_ID}>.")
        else:
            await safe_send(ctx, "❌ The channel could not be found. Contact an admin.")


async def setup(bot: commands.Bot):
    await bot.add_cog(LiveCog(bot))
