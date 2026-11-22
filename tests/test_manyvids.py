"""Unit tests for the ManyVids Agora integration."""

from __future__ import annotations

import time

from streamonitor.downloaders.agora import AgoraStream
from streamonitor.enums import Status
from streamonitor.sites.manyvids import ManyVids


class FakeResponse:
    def __init__(self, status_code=200, data=None, text="", headers=None):
        self.status_code = status_code
        self._data = data
        self.text = text
        self.headers = headers or {}

    def json(self):
        if self._data is None:
            raise ValueError("no json")
        return self._data


def patch_get(monkeypatch, bot, response):
    calls = []

    def get(url, **kwargs):
        calls.append((url, kwargs))
        return response

    monkeypatch.setattr(bot.session, "get", get)
    return calls


def test_status_public_and_safe_last_info(monkeypatch):
    bot = ManyVids("101")
    room = {
        "user_id": "101",
        "room_state": "ONLINE",
        "streaming_state": "PUBLIC",
        "creator_info": {"display_name": "Alice"},
        "token": "SECRET",
        "rtc": "SECRET",
    }
    calls = patch_get(monkeypatch, bot, FakeResponse(200, room))

    assert bot.getStatus() == Status.PUBLIC
    assert bot.lastInfo["streaming_state"] == "PUBLIC"
    assert "token" not in bot.lastInfo
    assert "rtc" not in bot.lastInfo
    assert "SECRET" not in repr(bot.lastInfo)
    headers = calls[0][1]["headers"]
    assert headers["Origin"] == "https://www.manyvids.com"
    assert headers["Referer"] == "https://www.manyvids.com/live/online"


def test_status_private(monkeypatch):
    bot = ManyVids("101")
    patch_get(monkeypatch, bot, FakeResponse(
        200, {"room_state": "ONLINE", "streaming_state": "PRIVATE"}))
    assert bot.getStatus() == Status.PRIVATE


def test_status_offline(monkeypatch):
    bot = ManyVids("101")
    patch_get(monkeypatch, bot, FakeResponse(
        200, {"room_state": "OFFLINE", "streaming_state": "PUBLIC"}))
    assert bot.getStatus() == Status.OFFLINE


def test_status_404_is_notexistent(monkeypatch):
    bot = ManyVids("101")
    calls = patch_get(monkeypatch, bot, FakeResponse(404))
    assert bot.getStatus() == Status.NOTEXIST
    assert len(calls) == 2


def test_status_403_is_restricted(monkeypatch):
    bot = ManyVids("101")
    patch_get(monkeypatch, bot, FakeResponse(403))
    assert bot.getStatus() == Status.RESTRICTED


def test_status_429_is_ratelimit(monkeypatch):
    bot = ManyVids("101")
    patch_get(monkeypatch, bot, FakeResponse(429))
    assert bot.getStatus() == Status.RATELIMIT


def test_status_other_errors_are_unknown(monkeypatch):
    bot = ManyVids("101")
    patch_get(monkeypatch, bot, FakeResponse(500))
    assert bot.getStatus() == Status.UNKNOWN

    bot = ManyVids("101")
    patch_get(monkeypatch, bot, FakeResponse(200, None, text="<html>"))
    assert bot.getStatus() == Status.UNKNOWN


def test_resolve_handle_from_profile_page(monkeypatch):
    bot = ManyVids("alice")
    responses = [
        FakeResponse(200, text='<script>{"roomId":"1011502633"}</script>'),
        FakeResponse(200, {"room_state": "ONLINE", "streaming_state": "PUBLIC"}),
    ]
    calls = []

    def get(url, **kwargs):
        calls.append(url)
        return responses.pop(0)

    monkeypatch.setattr(bot.session, "get", get)
    assert bot.getStatus() == Status.PUBLIC
    assert bot.user_id == "1011502633"
    assert calls[0] == "https://www.manyvids.com/live/cam/alice"
    assert calls[1] == "https://api.manyvids.com/live/room/1011502633"


def test_resolve_handle_from_profile_link(monkeypatch):
    """Current builds omit profileURL, so the handle-specific link is used."""
    bot = ManyVids("alice")
    html = (
        '<a href="/Profile/999/other/live">other</a>'
        '<a href="/Profile/101/alice/live">alice</a>'
    )
    responses = [
        FakeResponse(200, text=html),
        FakeResponse(200, {"room_state": "ONLINE", "streaming_state": "PUBLIC"}),
    ]
    monkeypatch.setattr(bot.session, "get", lambda *args, **kwargs: responses.pop(0))
    assert bot.getStatus() == Status.PUBLIC
    assert bot.user_id == "101"


def test_unparseable_profile_page_is_unknown(monkeypatch):
    bot = ManyVids("alice")
    patch_get(monkeypatch, bot, FakeResponse(200, text="<html>new layout</html>"))
    assert bot.getStatus() == Status.UNKNOWN


def test_join_channel_builds_credentials_and_refresh(monkeypatch):
    bot = ManyVids("alice")
    bot.user_id = "101"
    bot.lastInfo = {"streaming_state": "PUBLIC"}

    responses = [
        FakeResponse(200, {
            "meetingInfo": {
                "channelId": "channel-1",
                "rtc": "SECRET",
                "uid": 4118716069,
                "expires": 86400000,
            }
        }),
        FakeResponse(200, {
            "meetingInfo": {
                "channelId": "channel-1",
                "rtc": "SECOND",
                "uid": 4118716069,
                "expires": 86400000,
            }
        }),
    ]
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return responses.pop(0)

    monkeypatch.setattr(bot.session, "post", post)
    before = time.time()
    stream = bot.getVideoUrl()

    assert isinstance(stream, AgoraStream)
    assert stream.credentials.app_id == ManyVids.APP_ID
    assert stream.credentials.channel == "channel-1"
    assert stream.credentials.uid == 4118716069
    assert stream.credentials.token == "SECRET"
    assert stream.credentials.expires_at > before + 86000
    assert "SECRET" not in str(stream)
    assert "SECRET" not in repr(stream)
    assert calls[0][1]["json"] == {"visibility": "PUBLIC"}

    refreshed = stream.refresh()
    assert refreshed.token == "SECOND"
    assert refreshed.channel == "channel-1"


def test_join_channel_refuses_private_room(monkeypatch):
    bot = ManyVids("101")
    bot.lastInfo = {"streaming_state": "PRIVATE"}
    calls = []
    monkeypatch.setattr(bot.session, "post",
                        lambda *args, **kwargs: calls.append(args))
    assert bot.getVideoUrl() is None
    assert calls == []


def test_join_channel_requires_all_credentials(monkeypatch):
    bot = ManyVids("101")
    bot.lastInfo = {"streaming_state": "PUBLIC"}
    monkeypatch.setattr(
        bot.session, "post",
        lambda *args, **kwargs: FakeResponse(200, {
            "meetingInfo": {"channelId": "channel-1", "rtc": "SECRET"}
        }),
    )
    assert bot.getVideoUrl() is None


def test_join_channel_rejects_non_numeric_uid(monkeypatch):
    bot = ManyVids("101")
    bot.lastInfo = {"streaming_state": "PUBLIC"}
    monkeypatch.setattr(
        bot.session, "post",
        lambda *args, **kwargs: FakeResponse(200, {
            "meetingInfo": {
                "channelId": "channel-1", "rtc": "SECRET", "uid": "abc",
            }
        }),
    )
    assert bot.getVideoUrl() is None
