from discord.ext import commands

from modules.config import PROFILE_SPAM_CHANNEL_ID, STEAM_API_KEY
from modules.common import get_bot, safe_send
from modules.profiles import get_steam_profile_info, parse_steam_id


class SteamCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="steam")
    async def steam(self, ctx, *args):
        if not STEAM_API_KEY:
            await safe_send(ctx, "❌ Steam API key is missing. Add `STEAM_API_KEY` to `.env`.")
            return

        # Join the arguments so profile URLs and names both work
        if not args:
            await safe_send(ctx, "❌ Provide a SteamID or link.")
            return

        steam_input = " ".join(args)
        steam_id = await parse_steam_id(steam_input)

        if not steam_id:
            await safe_send(ctx, "❌ The SteamID could not be recognized.")
            return

        async with ctx.typing():
            info = await get_steam_profile_info(steam_id)

        msg = f"🕵️ **{info['username']}**\n"
        msg += f"🔗  [Steam profile]({info['profile_url']})\n"
        if info["profile_age"]:
            msg += f"📅  Account age: {info['profile_age']}\n"

        if info.get("private", False):
            # Don't continue with private profiles
            await safe_send(ctx, f"🔒 The profile is private or could not be found: {steam_input}")
            return

        if info["cs_hours"] > 0:
            msg += f"🕹️ CS hours: {info['cs_hours']}h\n"

        vac_status = "✅  No VAC bans" if not info["vac_banned"] else "🚫 VAC banned!"
        if info["vac_banned"] and info["days_since_ban"] is not None:
            vac_status += f" ({info['days_since_ban']} days ago)"

        game_bans = f"🎮  Game bans: {info['game_bans']}" if info["game_bans"] > 0 else "🎮  No game bans"
        msg += f"{vac_status}\n{game_bans}\n"

        if info["total_friends"] > 0:
            if info["banned_friends"] > 0:
                msg += f"👥 Friends (**{info['total_friends']}**) | Banned (**{info['banned_friends']}**)"
            else:
                msg += f"👥 Friends ({info['total_friends']})"

        bot = get_bot()
        channel = bot.get_channel(PROFILE_SPAM_CHANNEL_ID) if bot else None
        if channel:
            await safe_send(channel, msg)
            if getattr(ctx.channel, "id", None) != PROFILE_SPAM_CHANNEL_ID:
                await safe_send(ctx, f"✅ Profile posted to <#{PROFILE_SPAM_CHANNEL_ID}>.")
        else:
            await safe_send(ctx, "❌ The channel could not be found. Contact an admin.")


async def setup(bot: commands.Bot):
    await bot.add_cog(SteamCog(bot))
