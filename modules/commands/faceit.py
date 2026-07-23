from discord.ext import commands

from modules.config import FACEIT_API_KEY, PROFILE_SPAM_CHANNEL_ID
from modules.profiles import get_faceit_profile, parse_steam_id
from modules.common import get_bot, safe_send


class FaceitCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="faceit")
    async def faceit(self, ctx, *, steam_input):
        if not FACEIT_API_KEY:
            await safe_send(ctx, "❌ FACEIT API key is missing. Add `FACEIT_API_KEY` to `.env`.")
            return

        # Resolve the Steam input before querying FACEIT
        async with ctx.typing():
            steam_id = await parse_steam_id(steam_input)

        if not steam_id:
            await safe_send(ctx, "❌ The SteamID could not be recognized.")
            return

        result = await get_faceit_profile(steam_id)
        if isinstance(result, str):
            if result == "FACEIT profile not found.":
                await safe_send(ctx, "❌ FACEIT profile not found.")
            else:
                await safe_send(ctx, "❌ FACEIT lookup failed.")
            return

        msg = (
            f"**{result['nickname']}**\n"
            f"🌍  Country: {result['country'].upper()}\n"
            f"📅  Member since: {result['member_since']}\n"
            f"🎮  Faceit LVL: **{result['skill_level']}** | ELO: {result['elo']}\n"
            f"🎯  K/D: {result['kd']} | HS%: {result['hs']} | Win rate: {result['winrate']}\n"
            f"📊  Matches: {result['matches']} | 🔥 Longest win streak: {result['longest_win_streak']}\n"
            f"🔗  [Profile]({result['profile_url']})"
        )

        bot = get_bot()
        channel = bot.get_channel(PROFILE_SPAM_CHANNEL_ID) if bot else None
        if channel:
            await safe_send(channel, msg)
            if getattr(ctx.channel, "id", None) != PROFILE_SPAM_CHANNEL_ID:
                await safe_send(ctx, f"✅ Profile posted to <#{PROFILE_SPAM_CHANNEL_ID}>.")
        else:
            await safe_send(ctx, "❌ The channel could not be found. Contact an admin.")


async def setup(bot: commands.Bot):
    await bot.add_cog(FaceitCog(bot))
