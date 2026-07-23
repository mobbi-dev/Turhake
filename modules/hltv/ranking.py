import asyncio
import difflib
import re
import sqlite3
from datetime import datetime, date, time as dt_time, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from discord.ext import commands, tasks
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from modules.config import HLTV_RANKING_DEBUG_PORT, HLTV_RANKING_REFRESH_HOUR, HLTV_RANKING_REFRESH_MINUTE, HLTV_TEAMS_DB_FILE
from modules.hltv.common import chrome_options_factory, kill_orphan_chrome
from modules.common import log_to_channel, safe_send


RANKING_SOURCE_URL = "https://www.hltv.org/ranking/teams"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

_MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}

COMMON_TEAM_ALIASES = {
    "ence": "ENCE",
    "navi": "Natus Vincere",
}

_LATEST_RANKING_SNAPSHOT = None


def normalize_team_name(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower())


def _connect():
    conn = sqlite3.connect(HLTV_TEAMS_DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    HLTV_TEAMS_DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ranking_snapshots (
                snapshot_date TEXT PRIMARY KEY,
                source_url TEXT NOT NULL,
                fetched_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ranking_snapshot_teams (
                snapshot_date TEXT NOT NULL,
                position INTEGER NOT NULL,
                team_name TEXT NOT NULL,
                points INTEGER NOT NULL,
                team_profile_url TEXT,
                PRIMARY KEY (snapshot_date, position),
                FOREIGN KEY(snapshot_date) REFERENCES ranking_snapshots(snapshot_date) ON DELETE CASCADE
            )
            """
        )


def _parse_snapshot_date(text: str) -> Optional[date]:
    match = re.search(r"on\s+([A-Za-z]+)\s+(\d+)(?:st|nd|rd|th),\s+(\d{4})", text or "")
    if not match:
        return None

    month = _MONTHS.get(match.group(1).lower())
    if not month:
        return None

    return date(int(match.group(3)), month, int(match.group(2)))


def _parse_points(text: str) -> int:
    match = re.search(r"([\d,]+)", text or "")
    return int(match.group(1).replace(",", "")) if match else 0


def _parse_ranking_html(html: str, source_url: str) -> dict:
    # Extract the ranking header and team cards from the rendered page
    soup = BeautifulSoup(html, "html.parser")
    header = soup.select_one(".regional-ranking-header-text")
    header_text = header.get_text(" ", strip=True) if header else ""
    snapshot_date = _parse_snapshot_date(header_text) or datetime.now(timezone.utc).date()

    teams = []
    for box in soup.select(".ranked-team.standard-box"):
        position_elem = box.select_one(".ranking-header .position")
        team_name_elem = box.select_one(".teamLine .name")
        points_elem = box.select_one(".teamLine .points")

        if not (position_elem and team_name_elem and points_elem):
            continue

        position_text = position_elem.get_text(strip=True)
        position_match = re.search(r"(\d+)", position_text)
        if not position_match:
            continue

        team_profile_link = box.select_one(".more a.moreLink[href^='/team/']")
        team_profile_url = None
        if team_profile_link and team_profile_link.get("href"):
            team_profile_url = f"https://www.hltv.org{team_profile_link['href']}"

        teams.append(
            {
                "position": int(position_match.group(1)),
                "team_name": team_name_elem.get_text(" ", strip=True),
                "points": _parse_points(points_elem.get_text(" ", strip=True)),
                "team_profile_url": team_profile_url,
            }
        )

    return {
        "snapshot_date": snapshot_date.isoformat(),
        "source_url": source_url,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "teams": teams,
        "header_text": header_text,
    }


def _get_ranking_html():
    chrome_options = chrome_options_factory(port=HLTV_RANKING_DEBUG_PORT)

    driver = None
    try:
        kill_orphan_chrome(HLTV_RANKING_DEBUG_PORT)
        driver = webdriver.Chrome(options=chrome_options)
        driver.get(RANKING_SOURCE_URL)

        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".ranked-team.standard-box"))
            )
        except TimeoutException:
            return "", str(driver.current_url)

        return driver.page_source, str(driver.current_url)
    finally:
        if driver:
            driver.quit()


def _save_snapshot(snapshot: dict):
    # Store the latest ranking snapshot in SQLite and memory
    global _LATEST_RANKING_SNAPSHOT
    init_db()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO ranking_snapshots(snapshot_date, source_url, fetched_at)
            VALUES (?, ?, ?)
            ON CONFLICT(snapshot_date) DO UPDATE SET
                source_url = excluded.source_url,
                fetched_at = excluded.fetched_at
            """,
            (snapshot["snapshot_date"], snapshot["source_url"], snapshot["fetched_at"]),
        )
        conn.execute(
            "DELETE FROM ranking_snapshot_teams WHERE snapshot_date = ?",
            (snapshot["snapshot_date"],),
        )
        conn.executemany(
            """
            INSERT INTO ranking_snapshot_teams(snapshot_date, position, team_name, points, team_profile_url)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    snapshot["snapshot_date"],
                    team["position"],
                    team["team_name"],
                    team["points"],
                    team.get("team_profile_url"),
                )
                for team in snapshot["teams"]
            ],
        )
    _LATEST_RANKING_SNAPSHOT = snapshot


async def fetch_current_ranking_snapshot(source_url: str = RANKING_SOURCE_URL):
    # Run the browser scrape off the event loop thread
    html, final_url = await asyncio.to_thread(_get_ranking_html)
    if not html:
        raise RuntimeError("HLTV ranking page did not load")
    return _parse_ranking_html(html, final_url or source_url)


async def sync_current_ranking(source_url: str = RANKING_SOURCE_URL):
    try:
        # Refresh the cached ranking snapshot and report success to logs
        snapshot = await fetch_current_ranking_snapshot(source_url)
        _save_snapshot(snapshot)
        await log_to_channel(
            f"✅ HLTV ranking synced: {len(snapshot['teams'])} teams stored for {snapshot['snapshot_date']}"
        )
        return snapshot
    except Exception as exc:
        await log_to_channel(f"HLTV ranking sync error: {exc}")
        return None


def get_latest_ranking_snapshot():
    # Reuse the in-memory snapshot first -> then fall back to SQLite
    global _LATEST_RANKING_SNAPSHOT
    if _LATEST_RANKING_SNAPSHOT is not None:
        return _LATEST_RANKING_SNAPSHOT

    init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT snapshot_date, source_url, fetched_at FROM ranking_snapshots ORDER BY snapshot_date DESC LIMIT 1"
        ).fetchone()
        if not row:
            return None

        teams = conn.execute(
            """
            SELECT position, team_name, points, team_profile_url
            FROM ranking_snapshot_teams
            WHERE snapshot_date = ?
            ORDER BY position ASC
            """,
            (row["snapshot_date"],),
        ).fetchall()

    return {
        "snapshot_date": row["snapshot_date"],
        "source_url": row["source_url"],
        "fetched_at": row["fetched_at"],
        "teams": [dict(team) for team in teams],
    }


def get_latest_ranking_team_names():
    # Return only the canonical team names from the latest ranking
    snapshot = get_latest_ranking_snapshot()
    if not snapshot:
        return set()
    return {team["team_name"] for team in snapshot["teams"] if team.get("team_name")}


def get_latest_ranking_team_candidates():
    snapshot = get_latest_ranking_snapshot()
    if not snapshot:
        return []
    return [team["team_name"] for team in snapshot["teams"] if team.get("team_name")]


def resolve_ranking_team_name(team_query: str):
    # Resolve common aliases and exact ranking names first
    query = normalize_team_name(team_query)
    alias = COMMON_TEAM_ALIASES.get(query)
    if alias:
        return alias

    for candidate in get_latest_ranking_team_candidates():
        if normalize_team_name(candidate) == query:
            return candidate

    return None


def suggest_ranking_team_name(team_query: str):
    # Offer a close ranking match when the input is misspelled
    alias = resolve_ranking_team_name(team_query)
    if alias:
        return alias

    candidates = get_latest_ranking_team_candidates()
    if not candidates:
        return None

    query = normalize_team_name(team_query)
    matches = difflib.get_close_matches(query, [normalize_team_name(c) for c in candidates], n=1, cutoff=0.78)
    if not matches:
        return None

    lookup = {normalize_team_name(c): c for c in candidates}
    return lookup.get(matches[0])


class HLTVRankingScraper(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        # Start the scheduled ranking refresh loop
        if not self.refresh_ranking.is_running():
            self.refresh_ranking.start()

    def cog_unload(self):
        self.refresh_ranking.cancel()

    @tasks.loop(time=dt_time(hour=HLTV_RANKING_REFRESH_HOUR, minute=HLTV_RANKING_REFRESH_MINUTE, tzinfo=ZoneInfo("Europe/Helsinki")))
    async def refresh_ranking(self):
        # Only refresh on Monday evening: other days are intentional no-ops
        if datetime.now(ZoneInfo("Europe/Helsinki")).weekday() != 0:
            await log_to_channel("🔄 HLTV ranking refresh skipped: not Monday")
            return
        await sync_current_ranking()

    @refresh_ranking.before_loop
    async def before_refresh_ranking(self):
        await self.bot.wait_until_ready()

    @commands.command(name="hltvtop", hidden=True)
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def hltvtop(self, ctx: commands.Context):
        # Hidden admin command to fetch and print the current top teams
        await safe_send(ctx, "🔄 Fetching the HLTV top teams list...")
        snapshot = await sync_current_ranking()
        if not snapshot:
            await safe_send(ctx, "❌ Failed to fetch the HLTV ranking.")
            return

        teams = snapshot.get("teams", [])
        if not teams:
            await safe_send(ctx, "❌ The HLTV ranking did not contain any teams.")
            return

        lines = [f"#{team['position']} {team['team_name']} ({team['points']} pts)" for team in teams]
        message = "**HLTV top teams:**\n" + "\n".join(lines)

        if len(message) <= 2000:
            await safe_send(ctx, message)
            return

        chunk = "**HLTV top teams:**\n"
        for line in lines:
            if len(chunk) + len(line) + 1 > 2000:
                await safe_send(ctx, chunk)
                chunk = ""
            chunk += line + "\n"

        if chunk.strip():
            await safe_send(ctx, chunk.rstrip())


async def setup(bot: commands.Bot):
    # Load the ranking cache once on startup if needed
    init_db()
    snapshot = get_latest_ranking_snapshot()
    if snapshot is None:
        await log_to_channel("🔄 HLTV ranking cache empty on startup, fetching top teams...")
        await sync_current_ranking()
    else:
        await log_to_channel(
            f"✅ HLTV ranking loaded from cache: {len(snapshot['teams'])} teams for {snapshot['snapshot_date']}"
        )
    await bot.add_cog(HLTVRankingScraper(bot))
