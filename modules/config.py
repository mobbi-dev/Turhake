import os
from pathlib import Path


def _safe_int(key: str, default: str = "0") -> int:
    val = os.getenv(key)
    if val is None or val.strip() == "":
        return int(default)
    try:
        return int(val)
    except ValueError:
        print(f"WARNING: {key} is not a valid integer ('{val}'), using default {default}")
        return int(default)


# Common config values and file paths live here
MATCH_ANNOUNCE_CHANNEL_ID = _safe_int("MATCH_ANNOUNCE_CHANNEL_ID")
PROFILE_SPAM_CHANNEL_ID = _safe_int("PROFILE_SPAM_CHANNEL_ID")
LOGS_CHANNEL_ENABLED = os.getenv("LOGS_CHANNEL_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
LOGS_CHANNEL_ID = _safe_int("LOGS_CHANNEL_ID")
FREEGAMES_CHANNEL_ID = _safe_int("FREEGAMES_CHANNEL_ID")
CS2_UPDATES_CHANNEL_ID = _safe_int("CS2_UPDATES_CHANNEL_ID")

FREEGAMES_PRICE_CURRENCY = os.getenv("FREEGAMES_PRICE_CURRENCY", "eur").lower()

if FREEGAMES_PRICE_CURRENCY not in {"usd", "eur", "gbp"}:
    FREEGAMES_PRICE_CURRENCY = "eur"

HLTV_MAX_TRACKED_TEAMS = _safe_int("HLTV_MAX_TRACKED_TEAMS", "5")
HLTV_CACHE_EXPIRE_SECONDS = _safe_int("HLTV_CACHE_EXPIRE_SECONDS", "3600")
HLTV_REMOVE_MATCHES_OLDER_THAN_SECONDS = _safe_int("HLTV_REMOVE_MATCHES_OLDER_THAN_SECONDS", "10800")
HLTV_MATCH_ANNOUNCE_HOURS_BEFORE = _safe_int("HLTV_MATCH_ANNOUNCE_HOURS_BEFORE", "6")
HLTV_RANKING_REFRESH_HOUR = _safe_int("HLTV_RANKING_REFRESH_HOUR", "20")
HLTV_RANKING_REFRESH_MINUTE = _safe_int("HLTV_RANKING_REFRESH_MINUTE", "0")
HLTV_FETCH_POLL_MINUTES = _safe_int("HLTV_FETCH_POLL_MINUTES", "10")
HLTV_ANNOUNCE_POLL_MINUTES = _safe_int("HLTV_ANNOUNCE_POLL_MINUTES", "15")
FREEGAMES_POLL_MINUTES = _safe_int("FREEGAMES_POLL_MINUTES", "30")
CS2_UPDATES_POLL_MINUTES = _safe_int("CS2_UPDATES_POLL_MINUTES", "30")

HLTV_SCRAPING_DEBUG_PORT = _safe_int("HLTV_SCRAPING_DEBUG_PORT", "9222")
HLTV_RANKING_DEBUG_PORT = _safe_int("HLTV_RANKING_DEBUG_PORT", "9223")
HLTV_LIVE_DEBUG_PORT = _safe_int("HLTV_LIVE_DEBUG_PORT", "9224")
CS2_UPDATES_DEBUG_PORT = _safe_int("CS2_UPDATES_DEBUG_PORT", "9225")

CACHE_DIR = Path(__file__).resolve().parents[1] / "cache"
GIVEAWAY_CACHE_FILE = CACHE_DIR / "sent_giveaways.json"
CS2_UPDATES_CACHE_FILE = CACHE_DIR / "cs2_updates_cache.json"
HLTV_MATCHES_CACHE_FILE = CACHE_DIR / "hltv_matches_cache.json"
HLTV_TEAMS_DB_FILE = CACHE_DIR / "hltv_teams.sqlite3"

OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "")
FACEIT_API_KEY = os.getenv("FACEIT_API_KEY", "")
STEAM_API_KEY = os.getenv("STEAM_API_KEY", "")
