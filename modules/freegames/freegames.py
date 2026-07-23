import asyncio
import json
from datetime import datetime, timezone, timedelta
from typing import Optional

import aiohttp
import discord
from discord.ext import commands, tasks

from modules.config import FREEGAMES_CHANNEL_ID, FREEGAMES_POLL_MINUTES, FREEGAMES_PRICE_CURRENCY, GIVEAWAY_CACHE_FILE
from modules.common import log_to_channel, safe_send


EXCHANGE_RATE_URL = "https://api.frankfurter.app/latest?from=USD&to={target}"
_CURRENCY_SYMBOLS = {"usd": "$", "eur": "€", "gbp": "£"}


async def load_freegames_cache():
    # Load the giveaway cache from disk if it already exists
    if not GIVEAWAY_CACHE_FILE.is_file():
        return {}

    def _read_file():
        try:
            content = GIVEAWAY_CACHE_FILE.read_text(encoding="utf-8").strip()
            if not content:
                return {}
            return json.loads(content)
        except json.JSONDecodeError:
            return {}

    return await asyncio.to_thread(_read_file)


async def save_freegames_cache(cache):
    # Save the updated giveaway cache
    def _write_file():
        GIVEAWAY_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        GIVEAWAY_CACHE_FILE.write_text(
            json.dumps(cache, indent=2, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )

    await asyncio.to_thread(_write_file)


async def _get_usd_to_currency_rate(target_currency: str):
    # Convert the displayed value using the selected currency
    target_currency = target_currency.lower()
    if target_currency == "usd":
        return 1.0

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(EXCHANGE_RATE_URL.format(target=target_currency.upper()), timeout=15) as response:
                response.raise_for_status()
                data = await response.json()

        rates = data.get("rates") or {}
        return float(rates.get(target_currency.upper()))
    except Exception:
        return None


def _format_worth_currency(worth: str, currency: str, usd_to_currency_rate: Optional[float]):
    # Display the original price with a strikethrough in the selected currency
    if not worth or worth == "N/A":
        return "N/A"

    try:
        match = float(worth.replace("$", "").strip())
    except Exception:
        return worth

    currency = currency.lower()
    symbol = _CURRENCY_SYMBOLS.get(currency, "$")

    if currency == "usd":
        return f"~~{match:.2f}$~~"

    if usd_to_currency_rate is None:
        return f"~~{match:.2f}$~~"

    converted_value = round(match * usd_to_currency_rate, 2)
    return f"~~{converted_value:.2f}{symbol}~~"


class FreegamesCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        # Start the polling loop when the cog is loaded
        if not self.check_new_freegames.is_running():
            self.check_new_freegames.start()

    def cog_unload(self):
        self.check_new_freegames.cancel()

    @tasks.loop(minutes=FREEGAMES_POLL_MINUTES)
    async def check_new_freegames(self):
        try:
            # Fetch the current giveaways page and announce new entries
            print("Check free games from GamerPower API")

            channel = self.bot.get_channel(FREEGAMES_CHANNEL_ID)
            if not channel:
                print("❌ Channel not found.")
                return

            url = "https://www.gamerpower.com/api/giveaways"
            now = datetime.now(timezone.utc)

            freegames_cache = await load_freegames_cache()
            updated_cache = {}
            usd_to_currency_rate = await _get_usd_to_currency_rate(FREEGAMES_PRICE_CURRENCY)
            cache_skips = 0
            posted_count = 0

            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=20) as response:
                    if response.status != 200:
                        await log_to_channel("❌ GamerPower API error")
                        return

                    try:
                        giveaways = await response.json()
                    except Exception:
                        await log_to_channel("❌ JSON parse error")
                        return

            for game in giveaways:
                title = (game.get("title") or "").lower()
                platforms = game.get("platforms", "").lower()
                description = game.get("description", "").lower()

                if "itch.io" in title or "itch.io" in platforms or "itch.io" in description:
                    continue

                if any(x in title for x in ["mobile app", "chrome extension", "extension"]):
                    continue

                if game.get("type", "").upper() == "DLC":
                    continue

                giveaway_url = game.get("open_giveaway_url")
                if not giveaway_url:
                    continue

                if giveaway_url in freegames_cache:
                    # Keep existing giveaways in the cache without reposting
                    cache_skips += 1
                    updated_cache[giveaway_url] = freegames_cache[giveaway_url]
                    continue

                end_date_str = game.get("end_date")
                if not end_date_str or end_date_str.upper() == "N/A":
                    end_date = now + timedelta(days=7)
                else:
                    try:
                        end_date = datetime.strptime(end_date_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                    except Exception:
                        continue

                if end_date < now:
                    continue

                title = game.get("title", "Unknown Game")
                description = game.get("description", "")
                embed = discord.Embed(
                    title=title,
                    url=game["open_giveaway_url"],
                    description=(description[:100] + "...") if len(description) > 100 else description,
                    color=discord.Color.gold(),
                )

                if game.get("thumbnail"):
                    embed.set_image(url=game["thumbnail"])

                worth = game.get("worth") or "N/A"
                worth = _format_worth_currency(worth, FREEGAMES_PRICE_CURRENCY, usd_to_currency_rate)
                embed.add_field(name="Ends", value=end_date.strftime("%d.%m.%Y"), inline=True)
                embed.add_field(name="Value", value=worth, inline=True)
                embed.add_field(name="Platforms", value=game.get("platforms", "N/A"), inline=True)

                await safe_send(channel, "🎁 New free game available!", embed=embed)
                updated_cache[giveaway_url] = end_date.strftime("%Y-%m-%d %H:%M:%S")
                posted_count += 1

            await save_freegames_cache(updated_cache)
            await log_to_channel(
                f"✅ Freegames check completed: fetched={len(giveaways)}, posted={posted_count}, cache_skips={cache_skips}, currency={FREEGAMES_PRICE_CURRENCY}, rate={'N/A' if usd_to_currency_rate is None else f'{usd_to_currency_rate:.4f}'}"
            )

        except Exception:
            await log_to_channel("🔥 check_new_freegames crashed")

    @check_new_freegames.before_loop
    async def before_check_new_freegames(self):
        await self.bot.wait_until_ready()

    @check_new_freegames.error
    async def check_new_freegames_error(self, error):
        await log_to_channel("🔥 Loop error detected")


async def setup(bot: commands.Bot):
    # Register the cog and let it manage its own loop
    await bot.add_cog(FreegamesCog(bot))
