import aiohttp
from datetime import datetime

from modules.config import FACEIT_API_KEY
from modules.common import log_to_channel


async def get_faceit_profile(steam_id64):
    # Fetch FACEIT profile data and lifetime stats for Steam ID
    headers = {
        "Authorization": f"Bearer {FACEIT_API_KEY}"
    }

    player_url = f"https://open.faceit.com/data/v4/players?game=cs2&game_player_id={steam_id64}"
    async with aiohttp.ClientSession() as session:
        async with session.get(player_url, headers=headers) as response:
            if response.status != 200:
                if response.status == 404:
                    return "FACEIT profile not found."
                await log_to_channel("FACEIT player lookup failed")
                return "FACEIT lookup failed."
            data = await response.json()

    faceit_url = data.get("faceit_url", "").replace("{lang}/", "")
    nickname = data.get("nickname", "N/A")
    skill_level = data.get("games", {}).get("cs2", {}).get("skill_level", "N/A")
    elo = data.get("games", {}).get("cs2", {}).get("faceit_elo", "N/A")
    country = data.get("country", "N/A")
    player_id = data.get("player_id")

    activated_at_str = data.get("activated_at")
    profile_creation_date = "N/A"
    if activated_at_str:
        try:
            activated_datetime = datetime.fromisoformat(activated_at_str.replace('Z', '+00:00'))
            profile_creation_date = activated_datetime.strftime("%d.%m.%Y")
        except Exception:
            await log_to_channel("Error parsing FACEIT activation date")

    stats_url = f"https://open.faceit.com/data/v4/players/{player_id}/stats/cs2"
    async with aiohttp.ClientSession() as session:
        async with session.get(stats_url, headers=headers) as stats_resp:
            if stats_resp.status == 200:
                stats_data = await stats_resp.json()
                lifetime = stats_data.get("lifetime", {})
            else:
                lifetime = {}

    kd = hs = wr = matches = longest_ws = "N/A"
    if lifetime:
        kd_val = lifetime.get("Average K/D Ratio")
        if kd_val is not None:
            try:
                kd = f"{float(kd_val):.2f}"
            except:
                kd = kd_val

        hs_val = lifetime.get("Average Headshots %")
        if hs_val is not None:
            try:
                hs = f"{float(hs_val):.1f}%"
            except:
                hs = hs_val

        wr_val = lifetime.get("Win Rate %")
        if wr_val is not None:
            try:
                wr = f"{float(wr_val):.1f}%"
            except:
                wr = wr_val

        matches = lifetime.get("Matches", "N/A")
        longest_ws = lifetime.get("Longest Win Streak", "N/A")

    return {
        "nickname": nickname,
        "skill_level": skill_level,
        "elo": elo,
        "country": country,
        "profile_url": faceit_url,
        "kd": kd,
        "hs": hs,
        "winrate": wr,
        "matches": matches,
        "longest_win_streak": longest_ws,
        "member_since": profile_creation_date
    }
