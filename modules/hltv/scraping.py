import asyncio
import json
import re
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from modules.config import HLTV_CACHE_EXPIRE_SECONDS, HLTV_MATCHES_CACHE_FILE, HLTV_SCRAPING_DEBUG_PORT
from modules.hltv.common import chrome_options_factory, kill_orphan_chrome
from modules.hltv.team_admin import resolve_team_query
from modules.common import log_to_channel


HLTV_SCRAPE_TIMEOUT_SECONDS = 20
HLTV_SCRAPE_RETRY_DELAY_SECONDS = 3


def load_cache():
    # Cache the upcoming matches list to avoid scraping on every lookup
    if HLTV_MATCHES_CACHE_FILE.is_file():
        try:
            with HLTV_MATCHES_CACHE_FILE.open("r", encoding="utf-8") as f:
                content = f.read().strip()
                if not content:
                    return {"matches": [], "timestamp": 0, "announced": {}}
                cache = json.loads(content)
                if "announced" not in cache:
                    cache["announced"] = {}
                return cache
        except json.JSONDecodeError:
            return {"matches": [], "timestamp": 0, "announced": {}}
    return {"matches": [], "timestamp": 0, "announced": {}}


def save_cache(cache):
    # Save the HLTV match cache after each background refresh
    HLTV_MATCHES_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with HLTV_MATCHES_CACHE_FILE.open("w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False, sort_keys=True)


def get_upcoming_matches_raw():
    chrome_options = chrome_options_factory(port=HLTV_SCRAPING_DEBUG_PORT)

    driver = None
    try:
        kill_orphan_chrome(HLTV_SCRAPING_DEBUG_PORT)
        driver = webdriver.Chrome(options=chrome_options)
        driver.get("https://www.hltv.org/matches")

        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".match-wrapper[data-match-wrapper]"))
            )
        except TimeoutException:
            raise TimeoutException("Timed out waiting for HLTV match wrappers")

        soup = BeautifulSoup(driver.page_source, "html.parser")
        matches = []

        for match_elem in soup.select(".match-wrapper[data-match-wrapper]"):
            team1_elem = match_elem.select_one(".match-team.team1 .match-teamname")
            team2_elem = match_elem.select_one(".match-team.team2 .match-teamname")
            event_elem = match_elem.select_one(".match-event")
            timestamp_elem = match_elem.select_one(".match-time")
            bo_elem = match_elem.select_one(".match-meta")
            stage_elem = match_elem.select_one(".match-stage")

            event_name = "Unknown Event"
            if event_elem:
                event_name = event_elem.get("data-event-headline", "").strip() or event_elem.get_text(strip=True)
                if not event_name:
                    img_elem = event_elem.select_one(".match-event-logo")
                    if img_elem:
                        event_name = (img_elem.get("alt", "") or img_elem.get("title", "")).strip()
                if not event_name:
                    event_name = "Unknown Event"

            stage = ""
            if stage_elem:
                stage_text = stage_elem.get_text(strip=True).lower()
                if "grand final" in stage_text:
                    stage = "Grand Final"
                elif "semifinal" in stage_text:
                    stage = "Semifinal"
                elif "quarterfinal" in stage_text:
                    stage = "Quarterfinal"
                elif "playoff" in stage_text:
                    stage = "Playoffs"

            if not team2_elem:
                team2_elem = match_elem.select_one(".match-team.team2 .team")

            if not (team1_elem and team2_elem and timestamp_elem and timestamp_elem.get("data-unix")):
                continue

            start_time_utc = datetime.fromtimestamp(int(timestamp_elem["data-unix"]) / 1000, tz=timezone.utc)
            start_time_eet = start_time_utc.astimezone(ZoneInfo("Europe/Helsinki"))
            if start_time_utc < datetime.now(timezone.utc):
                continue

            matches.append({
                "id": match_elem.get("data-match-id", "0"),
                "team1": team1_elem.get_text(strip=True).lower(),
                "team2": team2_elem.get_text(strip=True).lower(),
                "event": event_name,
                "start_time": start_time_eet.isoformat(),
                "bo": bo_elem.get_text(strip=True).lower() if bo_elem else "bo1",
                "stage": stage,
            })

        if not matches:
            raise RuntimeError("HLTV scrape returned no matches")

        return matches
    except Exception:
        raise
    finally:
        if driver:
            driver.quit()


async def get_upcoming_matches_raw_async():
    # Run the blocking Selenium scrape in a worker thread
    last_error = None

    for attempt in range(2):
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(get_upcoming_matches_raw),
                timeout=HLTV_SCRAPE_TIMEOUT_SECONDS,
            )
        except Exception as e:
            last_error = e
            await log_to_channel(
                f"HLTV scrape failed on attempt {attempt + 1}/2: {type(e).__name__}: {e}"
            )
            kill_orphan_chrome(HLTV_SCRAPING_DEBUG_PORT)
            if attempt == 0:
                await asyncio.sleep(HLTV_SCRAPE_RETRY_DELAY_SECONDS)

    await log_to_channel(f"HLTV scrape failed after retries: {type(last_error).__name__}: {last_error}")
    return []


async def get_upcoming_matches_async():
    cache = await asyncio.to_thread(load_cache)
    now = time.time()
    now_dt = datetime.now(timezone.utc)

    if cache and "timestamp" in cache and "matches" in cache:
        if now - cache["timestamp"] < HLTV_CACHE_EXPIRE_SECONDS:
            matches = []
            for m in cache["matches"]:
                start = datetime.fromisoformat(m["start_time"])
                if start > now_dt:
                    m["start_time"] = start
                    matches.append(m)
            return matches

    matches_raw = await get_upcoming_matches_raw_async()
    upcoming_matches = []
    for m in matches_raw:
        start = datetime.fromisoformat(m["start_time"])
        if start > now_dt:
            upcoming_matches.append(m)

    for m in upcoming_matches:
        if isinstance(m["start_time"], str):
            m["start_time"] = datetime.fromisoformat(m["start_time"])

    return upcoming_matches


async def find_next_match_async(team_query, count=1):
    # Resolve aliases first, then filter upcoming matches for the team
    team_query = team_query.lower()
    team_name = resolve_team_query(team_query)
    matches = await get_upcoming_matches_async()

    def is_team_match(match_team: str, query: str):
        team = match_team.lower().strip()
        query = query.lower().strip()
        if team == query:
            return True
        banned_suffixes = [" nxt", " academy", " jr", " junior", " academy team", " academy roster"]
        if any(team.startswith(query + suffix) for suffix in banned_suffixes):
            return False
        if team.startswith("team ") and team.replace("team ", "") == query:
            return True
        return False

    future = [m for m in matches if is_team_match(m["team1"], team_name) or is_team_match(m["team2"], team_name)]
    return sorted(future, key=lambda x: x["start_time"])[:count]


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def format_match(match):
    localized = match["start_time"].astimezone(ZoneInfo("Europe/Helsinki"))
    time_str = localized.strftime("%d.%m.%Y %H:%M")
    tz_label = localized.strftime("%Z")
    slug = slugify(f"{match['team1']}-vs-{match['team2']}-{match['event']}")
    url = f"https://www.hltv.org/matches/{match['id']}/{slug}"

    team1_str = "TBD" if match["team1"].strip().lower() == "tbd" else match["team1"].title()
    team2_str = "TBD" if match["team2"].strip().lower() == "tbd" else match["team2"].title()
    bo = match.get("bo", "").upper()
    stage = match.get("stage", "").lower()
    stage_suffix = ""
    if stage == "grand final":
        stage_suffix = " - **Grand Final** 🏆"
    elif stage == "semifinal":
        stage_suffix = " - **Semifinal**"
    elif stage == "quarterfinal":
        stage_suffix = " - **Quarterfinal**"
    elif "playoff" in stage:
        stage_suffix = " - **Playoffs**"
    elif stage == "group stage":
        stage_suffix = " - **Group Stage**"

    return f"{match['event']}{stage_suffix}\n{team1_str} ⚔️ {team2_str} - **{bo.upper()}**\n⏰ {time_str} {tz_label}\n📎 {url}"
