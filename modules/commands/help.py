from discord.ext import commands

from modules.common import safe_send


class HelpCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="commands")
    async def commands_help(self, ctx):
        # Keep the public command list short and user-friendly
        help_text = (
            "**🤖 Commands:**\n"
            "`!cs [team]` - Shows the next CS match for a team in the match channel.\n"
            "`!cs [team] [count]` - Shows the next 1-3 CS matches for a team in the match channel.\n"
            "`!live [team]` - Checks whether a live match exists for that team. The result is posted in the match channel.\n"
            "`!weather [city]` - Current weather in a city.\n"
            "`!weather hourly [city]` - Hourly weather and precipitation for today.\n"
            "`!weather tomorrow [city]` - Tomorrow's average temperature and description.\n"
            "`!weather week [city]` - Daily weather forecast for the week.\n"
            "`!steam [steamID/link]` - Shows the Steam profile age and possible VAC/game bans. The result is posted in the profile channel.\n"
            "`!faceit [steamID/link]` - Shows the Faceit profile name, country, level, ELO, match count, and link. The result is posted in the profile channel.\n"
            "`!team add [name]` - Adds a HLTV team to the watchlist. Maximum 5 teams. Admin rights required.\n"
            "`!team list` - Shows the tracked HLTV teams.\n"
            "`!team remove [name]` - Removes a team from tracking. Admin rights required.\n"
            "**Note:** The bot fetches free games from the GamerPower API and posts them to the free games channel.\n"
        )
        await safe_send(ctx, help_text)


async def setup(bot: commands.Bot):
    await bot.add_cog(HelpCog(bot))
