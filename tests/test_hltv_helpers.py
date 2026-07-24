import asyncio
from datetime import date, datetime, timezone

from modules.hltv.ranking import _parse_points, _parse_ranking_html, _parse_snapshot_date
import modules.hltv.scraping as scraping
from modules.hltv.scraping import format_match, slugify


def test_parse_snapshot_and_points_helpers():
    assert _parse_snapshot_date("Top 30 on July 9th, 2026") == date(2026, 7, 9)
    assert _parse_points("1,234 points") == 1234
    assert _parse_points("no points") == 0


def test_parse_ranking_html_extracts_teams():
    html = """
    <div class="regional-ranking-header-text">HLTV ranking updated on July 9th, 2026</div>
    <div class="ranked-team standard-box">
      <div class="ranking-header"><div class="position">1</div></div>
      <div class="teamLine">
        <div class="name">Team Spirit</div>
        <div class="points">1000 points</div>
      </div>
      <div class="more"><a class="moreLink" href="/team/999/spirit"></a></div>
    </div>
    """

    parsed = _parse_ranking_html(html, "https://www.hltv.org/ranking/teams")
    assert parsed["snapshot_date"] == "2026-07-09"
    assert parsed["header_text"] == "HLTV ranking updated on July 9th, 2026"
    assert parsed["teams"] == [
        {
            "position": 1,
            "team_name": "Team Spirit",
            "points": 1000,
            "team_profile_url": "https://www.hltv.org/team/999/spirit",
        }
    ]


def test_hltv_slugify_and_match_formatting():
    match = {
        "id": "12345",
        "team1": "team spirit",
        "team2": "natus vincere",
        "event": "BLAST Premier",
        "start_time": datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc),
        "bo": "bo3",
        "stage": "playoffs",
    }

    assert slugify("Team Spirit vs NaVi") == "team-spirit-vs-navi"
    rendered = format_match(match)
    assert "Team Spirit ⚔️ Natus Vincere - **BO3**" in rendered
    assert "**Playoffs**" in rendered
    assert "https://www.hltv.org/matches/12345/team-spirit-vs-natus-vincere-blast-premier" in rendered


def test_hltv_scrape_async_retries_after_timeout(monkeypatch):
    calls = {"to_thread": 0, "kill": 0, "logs": []}

    async def fake_to_thread(func):
        calls["to_thread"] += 1
        if calls["to_thread"] == 1:
            raise asyncio.TimeoutError()
        return [
            {
                "id": "1",
                "team1": "team one",
                "team2": "team two",
                "event": "event",
                "start_time": datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc).isoformat(),
                "bo": "bo3",
                "stage": "",
            }
        ]

    async def fake_sleep(_):
        return None

    async def fake_log(message):
        calls["logs"].append(message)

    def fake_kill(*_args, **_kwargs):
        calls["kill"] += 1

    monkeypatch.setattr(scraping.asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr(scraping.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(scraping, "log_to_channel", fake_log)
    monkeypatch.setattr(scraping, "kill_orphan_chrome", fake_kill)

    result = asyncio.run(scraping.get_upcoming_matches_raw_async())

    assert calls["to_thread"] == 2
    assert calls["kill"] == 1
    assert len(result) == 1
    assert any("attempt 1/2" in message for message in calls["logs"])
