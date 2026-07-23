import re

from discord.ext import commands

from modules.config import MATCH_ANNOUNCE_CHANNEL_ID
from modules.hltv.scraping import find_next_match_async, format_match
from modules.common import get_bot, safe_send


class CSCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="cs")
    async def cs(self, ctx, *args):
        # Parse team name and optional match count from free-form args
        if not args:
            await safe_send(ctx, "❌ Provide a team name. Example: `!cs ence` or `!cs ence 2`")
            return

        team = None
        count = 1

        for arg in args:
            if re.fullmatch(r"\d+(-\d+)?", arg):
                match = re.match(r"(\d+)(?:-(\d+))?", arg)
                if match:
                    count = int(match.group(2) or match.group(1))
            else:
                team = arg

        if not team:
            await safe_send(ctx, "❌ Provide a team name. Example: `!cs ence` | `!cs 2 ence` | `!cs ence 2`")
            return

        matches = await find_next_match_async(team, count)

        if not matches:
            await safe_send(ctx, f"No upcoming matches were found for {team}.")
            return

        bot = get_bot()
        channel = bot.get_channel(MATCH_ANNOUNCE_CHANNEL_ID) if bot else None

        for i, match in enumerate(matches):
            msg = format_match(match)
            target = channel or ctx
            await safe_send(target, msg)

            if i < len(matches) - 1:
                await safe_send(target, "-" * 20)

        if channel:
            await safe_send(ctx, f"✅ Details posted to <#{MATCH_ANNOUNCE_CHANNEL_ID}>.")
        else:
            await safe_send(ctx, "❌ The match announcement channel could not be found.")


async def setup(bot: commands.Bot):
    await bot.add_cog(CSCog(bot))
