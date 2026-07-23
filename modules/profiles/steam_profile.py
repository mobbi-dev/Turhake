import asyncio
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

import aiohttp

from modules.config import STEAM_API_KEY
from modules.common import log_to_channel


async def parse_steam_id(steam_input):
    # Accept raw IDs, profile URLs, and vanity names
    steam_input = steam_input.strip()
    await log_to_channel("[parse_steam_id] Parsing Steam input")

    if steam_input.isdigit() and len(steam_input) >= 17:
        await log_to_channel("[parse_steam_id] Detected 64-bit Steam ID")
        return steam_input

    if "steamcommunity.com" in steam_input:
        parsed = urlparse(steam_input)
        path_parts = parsed.path.strip("/").split("/")
        await log_to_channel("[parse_steam_id] Parsed Steam URL")

        if len(path_parts) >= 2:
            if path_parts[0] == "profiles":
                await log_to_channel("[parse_steam_id] Extracted profile Steam ID")
                return path_parts[1]
            elif path_parts[0] == "id":
                vanity = path_parts[1]
                await log_to_channel("[parse_steam_id] Resolving vanity URL")
                return await resolve_vanity_url(vanity)

    if re.match(r"^[a-zA-Z0-9_-]+$", steam_input):
        await log_to_channel("[parse_steam_id] Looks like a vanity ID")
        return await resolve_vanity_url(steam_input)

    await log_to_channel("[parse_steam_id] Could not parse Steam ID")
    return None


async def resolve_vanity_url(vanity):
    # Resolve a Steam vanity URL to a 64-bit Steam ID
    url = f"http://api.steampowered.com/ISteamUser/ResolveVanityURL/v0001/?key={STEAM_API_KEY}&vanityurl={vanity}"
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("response", {}).get("success") == 1:
                        return data["response"]["steamid"]
                    else:
                        await log_to_channel("[resolve_vanity_url] Vanity lookup failed")
    except Exception:
        await log_to_channel("[resolve_vanity_url] ERROR")
    return None


async def get_steam_profile_info(steam_id64):
    # Gather Steam profile, ban, game time, and friend stats
    profile_url = f"https://steamcommunity.com/profiles/{steam_id64}"

    info = {
        "private": False,
        "profile_url": profile_url,
        "username": "Unknown",
        "cs_hours": 0,
        "vac_banned": False,
        "game_bans": 0,
        "days_since_ban": None,
        "profile_age": None,
        "total_friends": 0,
        "banned_friends": 0
    }

    timeout = aiohttp.ClientTimeout(total=10)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        try:
            summary_url = f"https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/?key={STEAM_API_KEY}&steamids={steam_id64}"
            async with session.get(summary_url) as resp:
                summary_response = await resp.json()

            players = summary_response.get("response", {}).get("players", [])
            if not players:
                info["private"] = True
                return info

            player = players[0]
            info["username"] = player.get("personaname", "Unknown user")
            visibility = player.get("communityvisibilitystate", 1)

            if visibility != 3:
                info["private"] = True
                return info

            created_unix = player.get("timecreated", 0)

            await asyncio.sleep(0.5)

            games_url = f"https://api.steampowered.com/IPlayerService/GetOwnedGames/v0001/?key={STEAM_API_KEY}&steamid={steam_id64}&format=json&include_appinfo=1"
            async with session.get(games_url) as resp:
                games_response = await resp.json()

            cs_hours = 0
            for game in games_response.get("response", {}).get("games", []):
                if game["appid"] in [730, 2279720]:
                    cs_hours = round(game["playtime_forever"] / 60)
                    break
            info["cs_hours"] = cs_hours

            await asyncio.sleep(0.5)

            bans_url = f"https://api.steampowered.com/ISteamUser/GetPlayerBans/v1/?key={STEAM_API_KEY}&steamids={steam_id64}"
            async with session.get(bans_url) as resp:
                bans_response = await resp.json()

            bans = bans_response.get("players", [{}])[0]
            info["vac_banned"] = bans.get("VACBanned", False)
            info["game_bans"] = bans.get("NumberOfGameBans", 0)
            info["days_since_ban"] = bans.get("DaysSinceLastBan", None)

            if created_unix:
                created_date = datetime.fromtimestamp(created_unix, tz=timezone.utc)
                now = datetime.now(timezone.utc)
                delta = now - created_date
                if delta.days < 365:
                    months = max(1, delta.days // 30)
                    unit = "month" if months == 1 else "months"
                    info["profile_age"] = f"{months} {unit}"
                else:
                    years = now.year - created_date.year
                    if (now.month, now.day) < (created_date.month, created_date.day):
                        years -= 1
                    unit = "year" if years == 1 else "years"
                    info["profile_age"] = f"{years} {unit}"

            await asyncio.sleep(0.5)

            friends_url = f"https://api.steampowered.com/ISteamUser/GetFriendList/v0001/?key={STEAM_API_KEY}&steamid={steam_id64}&relationship=friend"
            async with session.get(friends_url) as resp:
                friends_response = await resp.json()

            friends = friends_response.get("friendslist", {}).get("friends", [])
            info["total_friends"] = len(friends)

            await asyncio.sleep(1.5)

            banned_friends = 0
            for i in range(0, len(friends), 100):
                chunk = friends[i:i+100]
                ids_str = ",".join(friend["steamid"] for friend in chunk)
                bans_url_friends = f"https://api.steampowered.com/ISteamUser/GetPlayerBans/v1/?key={STEAM_API_KEY}&steamids={ids_str}"
                async with session.get(bans_url_friends) as resp:
                    bans_response_friends = await resp.json()
                for f in bans_response_friends.get("players", []):
                    if f.get("VACBanned") or f.get("NumberOfGameBans", 0) > 0:
                        banned_friends += 1

            info["banned_friends"] = banned_friends

        except Exception:
            await log_to_channel("Error in get_steam_profile_info")
            info["private"] = True

    return info
