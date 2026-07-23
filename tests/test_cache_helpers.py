import asyncio

from modules.cs2_updates.cs2_updates import CS2Updates
from modules.freegames import freegames as freegames_module
from modules.hltv import scraping as hltv_scraping


def test_freegames_cache_roundtrip(tmp_path, monkeypatch):
    cache_file = tmp_path / "freegames.json"
    monkeypatch.setattr(freegames_module, "GIVEAWAY_CACHE_FILE", cache_file)

    payload = {"https://example.com/game": "2026-07-20 12:00:00"}
    asyncio.run(freegames_module.save_freegames_cache(payload))

    assert asyncio.run(freegames_module.load_freegames_cache()) == payload


def test_hltv_cache_roundtrip(tmp_path, monkeypatch):
    cache_file = tmp_path / "hltv_matches.json"
    monkeypatch.setattr(hltv_scraping, "HLTV_MATCHES_CACHE_FILE", cache_file)

    payload = {"matches": [{"id": "1"}], "timestamp": 123, "announced": {"1": True}}
    hltv_scraping.save_cache(payload)

    assert hltv_scraping.load_cache() == payload


def test_cs2_cache_roundtrip(tmp_path, monkeypatch):
    cache_file = tmp_path / "cs2_updates.json"
    monkeypatch.setattr("modules.cs2_updates.cs2_updates.CS2_UPDATES_CACHE_FILE", cache_file)

    cog = CS2Updates(bot=None)
    payload = {"seen_ids": ["123", "456"]}

    cog._save_cache(payload)
    assert cog._load_cache() == payload
