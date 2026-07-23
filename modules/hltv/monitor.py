import asyncio
import time
from datetime import datetime, timezone

from discord.ext import commands, tasks

from modules.config import HLTV_ANNOUNCE_POLL_MINUTES, HLTV_FETCH_POLL_MINUTES, HLTV_MATCH_ANNOUNCE_HOURS_BEFORE, HLTV_REMOVE_MATCHES_OLDER_THAN_SECONDS, MATCH_ANNOUNCE_CHANNEL_ID
from modules.hltv.scraping import find_next_match_async, format_match, get_upcoming_matches_raw_async, load_cache, save_cache
from modules.hltv.team_admin import get_tracked_team_map, is_tracked_team
from modules.common import log_to_channel, safe_send


def format_time_change(old_time_str, new_time_str):
    # Show a compact before/after timestamp when HLTV changes a match
    try:
        old_dt = datetime.fromisoformat(old_time_str)
        new_dt = datetime.fromisoformat(new_time_str)
    except Exception:
        return f"{old_time_str} ➡️ {new_time_str}"

    if old_dt.date() == new_dt.date():
        date_str = f"{old_dt.day}.{old_dt.month}.{old_dt.year}"
        return f"{date_str} {old_dt.strftime('%H:%M')} ➡️ {new_dt.strftime('%H:%M')}"
    return f"{old_dt.day}.{old_dt.month}.{old_dt.year} {old_dt.strftime('%H:%M')} ➡️ {new_dt.day}.{new_dt.month}.{new_dt.year} {new_dt.strftime('%H:%M')}"


class HLTVMonitor(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        # Start both match background loops when the cog loads
        if not self.fetch_hltv_matches_periodically.is_running():
            self.fetch_hltv_matches_periodically.start()
        if not self.announce_matches.is_running():
            self.announce_matches.start()

    def cog_unload(self):
        self.fetch_hltv_matches_periodically.cancel()
        self.announce_matches.cancel()

    async def _log_match_update(self, match, message: str):
        # Send tracked-team changes to the announce channel and everything else to logs channel
        announce_channel = self.bot.get_channel(MATCH_ANNOUNCE_CHANNEL_ID)

        if is_tracked_team(match.get("team1", "")) or is_tracked_team(match.get("team2", "")):
            if announce_channel:
                await safe_send(announce_channel, message)
            else:
                print(f"[ANNOUNCE] {message}")
        else:
            await log_to_channel(message)

    @tasks.loop(minutes=HLTV_FETCH_POLL_MINUTES)
    async def fetch_hltv_matches_periodically(self):
        try:
            # Refresh the match cache and diff it against the previous snapshot
            print("Fetching HLTV matches in background task...")
            start_time_fetch = time.perf_counter()
            new_matches = await get_upcoming_matches_raw_async()
            end_time_fetch = time.perf_counter()

            fetch_duration_ms = (end_time_fetch - start_time_fetch) * 1000
            log_message = f"Fetched {len(new_matches)} matches from HLTV. It took {fetch_duration_ms:.2f} ms to retrieve HLTV data."
            print(log_message)
            await log_to_channel(log_message)

            cache = await asyncio.to_thread(load_cache)
            current_matches = cache.get("matches", [])
            announced = cache.get("announced", {})
            signatures = cache.get("signatures", {})

            updated_matches_dict = {m["id"]: m for m in current_matches}
            matches_updated_count = 0
            new_matches_count = 0

            for new_match in new_matches:
                match_id = new_match["id"]
                old_match = updated_matches_dict.get(match_id)

                if old_match:
                    original_old_match = dict(old_match)
                    changes = []

                    old_event = old_match.get("event") or ""
                    new_event = new_match.get("event") or ""

                    if old_event == "Unknown Event" and new_event != "Unknown Event":
                        old_match["event"] = new_event
                        changes.append(f"**Event:** {old_event} ➡️ {new_event} - **ID:** {match_id}")

                    original_old_event_for_log = old_event

                    team1 = new_match["team1"].upper()
                    team2 = new_match["team2"].upper()
                    teams_str = f"{team1} vs {team2}"

                    old_teams_str = f"{old_match['team1'].upper()} vs {old_match['team2'].upper()}"
                    if teams_str != old_teams_str:
                        old_match["team1"] = new_match["team1"]
                        old_match["team2"] = new_match["team2"]
                        changes.append(f"**Teams:** {old_teams_str} ➡️ {teams_str}")

                    old_bo = (old_match.get("bo") or "").upper()
                    new_bo = (new_match.get("bo") or "").upper()
                    if old_bo != new_bo:
                        old_match["bo"] = new_match["bo"]
                        changes.append(f"**BO:** {old_bo} ➡️ {new_bo}")

                    old_time = old_match.get("start_time") or ""
                    new_time = new_match.get("start_time") or ""
                    if old_time != new_time:
                        old_match["start_time"] = new_time
                        if not any("**Teams:**" in c for c in changes):
                            changes.insert(0, f"**Teams:** {teams_str}")
                        changes.append(f"**Starting time:** {format_time_change(old_time, new_time)}")

                    if changes:
                        new_signature = f"{new_match['team1'].lower()} vs {new_match['team2'].lower()}|{new_match['start_time']}|{new_match.get('bo', '').lower()}|{new_match.get('event', '')}"
                        old_signature = f"{original_old_match['team1'].lower()} vs {original_old_match['team2'].lower()}|{original_old_match['start_time']}|{original_old_match.get('bo', '').lower()}|{original_old_match.get('event', '')}"

                        if new_signature != old_signature:
                            msg = f"🔁 Match information updated ({original_old_event_for_log}):\n" + "\n".join(changes)
                            await self._log_match_update(new_match, msg)
                            matches_updated_count += 1
                            signatures[match_id] = new_signature
                        else:
                            await log_to_channel(f"No meaningful update for match {match_id}; signature unchanged.")

                    updated_matches_dict[match_id] = old_match
                else:
                    updated_matches_dict[match_id] = new_match
                    new_matches_count += 1

                    team1 = new_match["team1"]
                    team2 = new_match["team2"]
                    bo = new_match.get("bo", "")
                    event = new_match.get("event", "")
                    start_time = new_match.get("start_time", "")

                    announcement_signature = f"{team1.lower()} vs {team2.lower()}|{start_time}|{bo.lower()}|{event}"
                    cache_key = str(match_id)

                    start_dt = datetime.fromisoformat(start_time)
                    formatted_start = f"{start_dt.day}.{start_dt.month}.{start_dt.year} {start_dt.strftime('%H:%M')}"
                    formatted_teams = f"{team1.upper()} vs {team2.upper()}"

                    already_fetched_same = signatures.get(cache_key) == announcement_signature
                    if not already_fetched_same:
                        msg = f"🆕 New match added: **{formatted_teams}** ({event})\n🕒 Starts at: {formatted_start} | BO: {bo.upper()}"
                        await log_to_channel(msg)
                        signatures[cache_key] = announcement_signature

            if matches_updated_count > 0:
                await log_to_channel(f"Updated {matches_updated_count} matches in the cache file.")

            if new_matches_count > 0:
                await log_to_channel(f"Added {new_matches_count} new matches to the cache.")

            now_dt = datetime.now(timezone.utc)
            filtered_matches = []
            valid_ids = set()

            for m in updated_matches_dict.values():
                start = datetime.fromisoformat(m["start_time"])
                age_seconds = (now_dt - start).total_seconds()
                if start > now_dt or age_seconds <= HLTV_REMOVE_MATCHES_OLDER_THAN_SECONDS:
                    filtered_matches.append(m)
                    valid_ids.add(str(m["id"]))

            cache["announced"] = {k: v for k, v in announced.items() if k in valid_ids}
            cache["signatures"] = {k: v for k, v in signatures.items() if k in valid_ids}
            cache["matches"] = filtered_matches
            cache["timestamp"] = time.time()

            await asyncio.to_thread(save_cache, cache)

        except Exception as e:
            error_msg = f"Error fetching HLTV matches: {e}"
            print(error_msg)
            await log_to_channel(error_msg)

    @fetch_hltv_matches_periodically.before_loop
    async def before_fetch_hltv_matches(self):
        await self.bot.wait_until_ready()

    @tasks.loop(minutes=HLTV_ANNOUNCE_POLL_MINUTES)
    async def announce_matches(self):
        cache = await asyncio.to_thread(load_cache)
        channel = self.bot.get_channel(MATCH_ANNOUNCE_CHANNEL_ID)
        if not channel:
            await log_to_channel(f"HLTV announce channel missing: {MATCH_ANNOUNCE_CHANNEL_ID}")
            return

        if not cache.get("matches"):
            return

        teams = get_tracked_team_map()
        announced_ids = cache.get("announced", {})

        for canonical_name, aliases in teams.items():
            matches = []
            for alias in {canonical_name, *aliases}:
                matches = await find_next_match_async(alias)
                if matches:
                    break
            if not matches:
                continue

            now = datetime.now(timezone.utc)
            for match in matches:
                match_id = str(match["id"])
                if match_id in announced_ids:
                    continue
                if 0 < (match["start_time"] - now).total_seconds() <= HLTV_MATCH_ANNOUNCE_HOURS_BEFORE * 3600:
                    await safe_send(channel, f"🎮 Upcoming match: {format_match(match)}")
                    announced_ids[match_id] = True

        cache["announced"] = announced_ids
        await asyncio.to_thread(save_cache, cache)

    @announce_matches.before_loop
    async def before_announce_matches(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    # Register the cog
    await bot.add_cog(HLTVMonitor(bot))
