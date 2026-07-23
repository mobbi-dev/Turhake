import difflib
import json
import re
import sqlite3
from threading import RLock
from typing import Optional

from discord.ext import commands

from modules.config import HLTV_MATCHES_CACHE_FILE, HLTV_MAX_TRACKED_TEAMS, HLTV_TEAMS_DB_FILE
from modules.hltv.ranking import get_latest_ranking_team_names, resolve_ranking_team_name, suggest_ranking_team_name, sync_current_ranking
from modules.common import safe_send


_TRACKED_TEAM_CACHE = None
_TEAM_CANDIDATE_CACHE = {"signature": None, "candidates": [], "lookup": {}}
_CACHE_LOCK = RLock()


def normalize_team_name(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower())


def canonicalize_team_name(name: str) -> str:
    ranking_name = resolve_ranking_team_name(name)
    return ranking_name or name.strip()


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
            CREATE TABLE IF NOT EXISTS tracked_teams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                canonical_name TEXT NOT NULL UNIQUE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tracked_team_aliases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_id INTEGER NOT NULL,
                alias TEXT NOT NULL UNIQUE,
                FOREIGN KEY(team_id) REFERENCES tracked_teams(id) ON DELETE CASCADE
            )
            """
        )


def _load_tracked_team_cache():
    # Load tracked teams and aliases from SQLite into memory
    global _TRACKED_TEAM_CACHE
    init_db()
    with _connect() as conn:
        teams = conn.execute("SELECT id, canonical_name FROM tracked_teams ORDER BY canonical_name COLLATE NOCASE").fetchall()
        aliases = conn.execute("SELECT team_id, alias FROM tracked_team_aliases").fetchall()

    cache = {}
    id_to_name = {}
    for row in teams:
        canonical = canonicalize_team_name(row["canonical_name"])
        cache[canonical] = set()
        id_to_name[row["id"]] = canonical

    for row in aliases:
        canonical = id_to_name.get(row["team_id"])
        if canonical:
            cache.setdefault(canonical, set()).add(row["alias"])

    with _CACHE_LOCK:
        _TRACKED_TEAM_CACHE = cache
        return cache


def _get_tracked_team_cache():
    # Reuse the in-memory tracked-team cache when possible
    global _TRACKED_TEAM_CACHE
    with _CACHE_LOCK:
        if _TRACKED_TEAM_CACHE is None:
            return _load_tracked_team_cache()
        return _TRACKED_TEAM_CACHE


def _sort_tracked_team_cache(cache):
    return {canonical: cache[canonical] for canonical in sorted(cache.keys(), key=lambda x: x.lower())}


def _get_team_candidate_signature():
    # Build a simple signature so we only rebuild candidates when inputs change
    tracked = _get_tracked_team_cache()
    tracked_signature = tuple(
        sorted(
            (
                normalize_team_name(canonical),
                tuple(sorted(aliases)),
            )
            for canonical, aliases in tracked.items()
        )
    )

    ranking_snapshot = get_latest_ranking_team_names()
    ranking_signature = tuple(sorted(normalize_team_name(name) for name in ranking_snapshot))

    match_mtime = 0.0
    if HLTV_MATCHES_CACHE_FILE.is_file():
        try:
            match_mtime = HLTV_MATCHES_CACHE_FILE.stat().st_mtime
        except Exception:
            match_mtime = 0.0

    return tracked_signature, ranking_signature, match_mtime


def _build_team_candidate_cache():
    # Merge match cache, ranking names, and tracked aliases into one lookup table
    global _TEAM_CANDIDATE_CACHE
    candidates = {}

    for name in _load_cache_teams():
        candidates[normalize_team_name(name)] = name

    for name in get_latest_ranking_team_names():
        candidates.setdefault(normalize_team_name(name), name)

    tracked = get_tracked_team_map()
    for name, aliases in tracked.items():
        candidates[normalize_team_name(name)] = name
        for alias in aliases:
            candidates[normalize_team_name(alias)] = name

    sorted_candidates = [candidates[key] for key in sorted(candidates.keys())]
    with _CACHE_LOCK:
        _TEAM_CANDIDATE_CACHE = {
            "signature": _get_team_candidate_signature(),
            "candidates": sorted_candidates,
            "lookup": candidates,
        }
        return _TEAM_CANDIDATE_CACHE


def _get_team_candidate_cache():
    # Rebuild the candidate cache only when its signature changes
    signature = _get_team_candidate_signature()
    with _CACHE_LOCK:
        if _TEAM_CANDIDATE_CACHE["signature"] != signature:
            return _build_team_candidate_cache()
        return _TEAM_CANDIDATE_CACHE


def _find_cached_team(team_name: str):
    query = normalize_team_name(team_name)
    cache = _get_tracked_team_cache()
    for canonical, aliases in cache.items():
        if normalize_team_name(canonical) == query or query in aliases:
            return canonical
    return None


def _upsert_tracked_team_cache(canonical_name: str, alias: Optional[str] = None):
    # Update the in-memory tracked-team cache after an add
    global _TRACKED_TEAM_CACHE
    global _TEAM_CANDIDATE_CACHE
    with _CACHE_LOCK:
        cache = _get_tracked_team_cache()
        canonical = canonicalize_team_name(canonical_name)
        canonical_norm = normalize_team_name(canonical)

        existing_key = None
        for key in list(cache.keys()):
            if normalize_team_name(key) == canonical_norm:
                existing_key = key
                break

        aliases = set()
        if existing_key is not None:
            aliases = set(cache.pop(existing_key))

        if alias:
            alias_norm = normalize_team_name(alias)
            if alias_norm != canonical_norm:
                aliases.add(alias_norm)

        cache[canonical] = aliases
        _TRACKED_TEAM_CACHE = cache
        _TEAM_CANDIDATE_CACHE["signature"] = None


def _remove_tracked_team_cache(team_name: str):
    # Update the in-memory tracked-team cache after a remove
    global _TRACKED_TEAM_CACHE
    global _TEAM_CANDIDATE_CACHE
    with _CACHE_LOCK:
        cache = _get_tracked_team_cache()
        query = normalize_team_name(team_name)
        for canonical in list(cache.keys()):
            aliases = cache[canonical]
            if normalize_team_name(canonical) == query or query in aliases:
                cache.pop(canonical, None)
                _TRACKED_TEAM_CACHE = cache
                _TEAM_CANDIDATE_CACHE["signature"] = None
                return canonical
        return None


def get_tracked_team_map():
    # Return tracked teams sorted for stable list output
    return _sort_tracked_team_cache(_get_tracked_team_cache())


def get_tracked_team_names():
    return set(get_tracked_team_map().keys())


def get_tracked_team_count():
    # Count tracked teams from memory instead of re-reading SQLite
    return len(_get_tracked_team_cache())


def is_team_already_tracked(team_name: str):
    return _find_cached_team(team_name)


def is_tracked_team(team_name: str) -> bool:
    return is_team_already_tracked(team_name) is not None


def resolve_team_query(team_query: str):
    query = normalize_team_name(team_query)
    tracked = _get_tracked_team_cache()

    for canonical, aliases in tracked.items():
        if normalize_team_name(canonical) == query or query in aliases:
            return canonical

    return canonicalize_team_name(team_query)


def _load_cache_teams():
    if not HLTV_MATCHES_CACHE_FILE.is_file():
        return set()

    try:
        with HLTV_MATCHES_CACHE_FILE.open("r", encoding="utf-8") as f:
            cache = json.load(f)
    except Exception:
        return set()

    teams = set()
    for match in cache.get("matches", []):
        team1 = (match.get("team1") or "").strip()
        team2 = (match.get("team2") or "").strip()
        if team1:
            teams.add(team1)
        if team2:
            teams.add(team2)
    return teams


def get_team_candidates():
    # Return cached candidate names for typo suggestions
    return list(_get_team_candidate_cache()["candidates"])


def find_exact_team_match(team_query: str):
    # Check the cached candidate lookup first
    query = normalize_team_name(team_query)
    return _get_team_candidate_cache()["lookup"].get(query)


def suggest_team_name(team_query: str):
    # Use fuzzy matching to suggest the closest known team
    cache = _get_team_candidate_cache()
    candidates = cache["candidates"]
    if not candidates:
        return suggest_ranking_team_name(team_query)

    query = normalize_team_name(team_query)
    normalized_candidates = [normalize_team_name(c) for c in candidates]
    matches = difflib.get_close_matches(query, normalized_candidates, n=1, cutoff=0.68)
    if not matches:
        best_candidate = None
        best_ratio = 0.0
        for candidate in candidates:
            ratio = difflib.SequenceMatcher(None, query, normalize_team_name(candidate)).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_candidate = candidate

        if best_candidate and best_ratio >= 0.68:
            return best_candidate

        return suggest_ranking_team_name(team_query)

    return cache["lookup"].get(matches[0]) or suggest_ranking_team_name(team_query)


def add_tracked_team(team_name: str, alias: Optional[str] = None):
    # Save the team to SQLite and refresh the in-memory cache
    init_db()
    canonical = canonicalize_team_name(team_name)
    alias_norm = normalize_team_name(alias) if alias else None

    with _connect() as conn:
        row = conn.execute(
            "SELECT id, canonical_name FROM tracked_teams WHERE lower(canonical_name) = lower(?)",
            (canonical,),
        ).fetchone()

        if row:
            team_id = row["id"]
            if row["canonical_name"] != canonical:
                conn.execute(
                    "UPDATE tracked_teams SET canonical_name = ? WHERE id = ?",
                    (canonical, team_id),
                )
        else:
            conn.execute(
                "INSERT INTO tracked_teams(canonical_name) VALUES (?)",
                (canonical,),
            )
            team_id = conn.execute(
                "SELECT id FROM tracked_teams WHERE canonical_name = ?",
                (canonical,),
            ).fetchone()["id"]

        if alias_norm and alias_norm != normalize_team_name(canonical):
            conn.execute(
                "INSERT OR IGNORE INTO tracked_team_aliases(team_id, alias) VALUES (?, ?)",
                (team_id, alias_norm),
            )

    _upsert_tracked_team_cache(canonical, alias)


def remove_tracked_team(team_name: str):
    # Remove a team by canonical name or alias and refresh the cache
    init_db()
    query = normalize_team_name(team_name)
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, canonical_name FROM tracked_teams WHERE lower(canonical_name) = lower(?)",
            (canonicalize_team_name(team_name),),
        ).fetchone()

        if not row:
            row = conn.execute(
                """
                SELECT tracked_teams.id, tracked_teams.canonical_name
                FROM tracked_team_aliases
                JOIN tracked_teams ON tracked_team_aliases.team_id = tracked_teams.id
                WHERE tracked_team_aliases.alias = ?
                """,
                (query,),
            ).fetchone()

        if row:
            conn.execute("DELETE FROM tracked_teams WHERE id = ?", (row["id"],))
            removed = _remove_tracked_team_cache(team_name) or row["canonical_name"]
            return removed
        return False


class HLTVTeamAdmin(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.group(name="team", invoke_without_command=True)
    async def team(self, ctx: commands.Context):
        await safe_send(ctx, "Usage: `!team add <name>`, `!team list`, `!team remove <name>`")

    @team.command(name="add")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def team_add(self, ctx: commands.Context, *, team_name: str):
        already_tracked = is_team_already_tracked(team_name)
        if already_tracked:
            await safe_send(ctx, f"❌ Team **{already_tracked}** is already being tracked.")
            return

        if get_tracked_team_count() >= HLTV_MAX_TRACKED_TEAMS:
            await safe_send(ctx, f"❌ You can track at most {HLTV_MAX_TRACKED_TEAMS} teams.")
            return

        resolved = resolve_ranking_team_name(team_name) or resolve_team_query(team_name)
        exact_known = find_exact_team_match(team_name) or resolve_ranking_team_name(team_name)
        suggestion = suggest_team_name(team_name)

        if not exact_known and not suggestion and not get_latest_ranking_team_names():
            await sync_current_ranking()
            exact_known = find_exact_team_match(team_name) or resolve_ranking_team_name(team_name)
            suggestion = suggest_team_name(team_name)

        if normalize_team_name(resolved) != normalize_team_name(team_name):
            add_tracked_team(resolved, alias=team_name)
            await safe_send(ctx, f"✅ Added to watchlist: **{resolved}** (alias: `{team_name}`)")
            return

        if exact_known:
            alias_value = None if normalize_team_name(exact_known) == normalize_team_name(team_name) else team_name
            add_tracked_team(exact_known, alias=alias_value)
            await safe_send(ctx, f"✅ Added to watchlist: **{exact_known}**")
            return

        if suggestion:
            await safe_send(ctx, f"❌ Team `{team_name}` was not found. Did you mean `{suggestion}`?")
            return

        await safe_send(ctx, f"❌ Team `{team_name}` was not found among HLTV's known teams.")

    @team.command(name="list")
    @commands.guild_only()
    async def team_list(self, ctx: commands.Context):
        # Show the cached tracked teams with their aliases
        tracked = get_tracked_team_map()
        if not tracked:
            await safe_send(ctx, "No tracked teams.")
            return

        lines = []
        for canonical, aliases in tracked.items():
            alias_text = ", ".join(sorted(aliases)) if aliases else "-"
            lines.append(f"- {canonical} [{alias_text}]")

        await safe_send(ctx, "**Tracked teams:**\n" + "\n".join(lines))

    @team.command(name="remove")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def team_remove(self, ctx: commands.Context, *, team_name: str):
        # Remove by canonical name or alias
        removed = remove_tracked_team(team_name)
        if not removed:
            await safe_send(ctx, f"❌ Team `{team_name}` is not being tracked.")
            return
        await safe_send(ctx, f"🗑️ Removed from watchlist: **{removed}**")


async def setup(bot: commands.Bot):
    # Initialize the database and register the cog
    init_db()
    await bot.add_cog(HLTVTeamAdmin(bot))
