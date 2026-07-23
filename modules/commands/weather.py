import asyncio

from discord.ext import commands

from modules.config import OPENWEATHER_API_KEY
from modules.common import safe_send
from modules.weather import get_hourly_weather, get_weather, get_weather_tomorrow, get_weather_week


class WeatherCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="weather")
    async def weather(self, ctx, *args):
        if not OPENWEATHER_API_KEY:
            await safe_send(ctx, "❌ OpenWeather API key is missing. Add `OPENWEATHER_API_KEY` to `.env`.")
            return

        if not args:
            await safe_send(ctx, "❗ Provide a city. Example: `!weather Helsinki` or `!weather tomorrow Tampere`.")
            return

        reserved = {"tomorrow", "week", "hourly"}
        action = args[0].lower()

        if action not in reserved and any(arg.lower() in reserved for arg in args[1:]):
            await safe_send(ctx, "❗ Use `!weather <city>`, `!weather tomorrow <city>`, `!weather week <city>`, or `!weather hourly <city>`.")
            return

        if action == "tomorrow":
            city = " ".join(args[1:])
            if not city:
                await safe_send(ctx, "❗ Provide a city. Example: `!weather tomorrow Helsinki`")
                return
            result = await asyncio.to_thread(get_weather_tomorrow, city)
        elif action == "week":
            city = " ".join(args[1:])
            if not city:
                await safe_send(ctx, "❗ Provide a city. Example: `!weather week Helsinki`")
                return
            result = await asyncio.to_thread(get_weather_week, city)
        elif action == "hourly":
            city = " ".join(args[1:])
            if not city:
                await safe_send(ctx, "❗ Provide a city. Example: `!weather hourly Helsinki`")
                return
            result = await asyncio.to_thread(get_hourly_weather, city)
        else:
            city = " ".join(args)
            result = await asyncio.to_thread(get_weather, city)

        await safe_send(ctx, result)


async def setup(bot: commands.Bot):
    await bot.add_cog(WeatherCog(bot))
