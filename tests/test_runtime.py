import asyncio
import pytest
import modules.common.runtime as runtime


class _FailingChannel:
    id = 123

    async def send(self, *args, **kwargs):
        raise RuntimeError("temporary discord failure")


class _FakeBot:
    def __init__(self, channel):
        self._channel = channel

    def get_channel(self, channel_id):
        return self._channel if channel_id == 999 else None


def test_safe_send_swallows_send_failures():
    result = asyncio.run(runtime.safe_send(_FailingChannel(), "hello"))
    assert result is None


def test_log_to_channel_does_not_raise_when_send_fails(monkeypatch):
    monkeypatch.setattr(runtime, "LOGS_CHANNEL_ENABLED", True)
    monkeypatch.setattr(runtime, "LOGS_CHANNEL_ID", 999)
    monkeypatch.setattr(runtime, "_bot", _FakeBot(_FailingChannel()))

    asyncio.run(runtime.log_to_channel("background task message"))
