from unittest.mock import patch, MagicMock
import os
from pathlib import Path
from types import SimpleNamespace

from streamonitor.enums import Status, Gender
from streamonitor.sites.myfreecams import MyFreeCams


def test_mfc_parse_status():
    # Public
    assert MyFreeCams._parse_model_status({'vs': 0, 'u': {'camserv': 1234}}) == Status.PUBLIC
    assert MyFreeCams._parse_model_status({'vs': 90, 'u': {'camserv': 1234}}) == Status.PUBLIC
    
    # Offline when camserv is 0 or missing
    assert MyFreeCams._parse_model_status({'vs': 0, 'u': {'camserv': 0}}) == Status.OFFLINE
    assert MyFreeCams._parse_model_status({'vs': 90, 'u': {}}) == Status.OFFLINE
    assert MyFreeCams._parse_model_status({'vs': 127}) == Status.OFFLINE
    assert MyFreeCams._parse_model_status({'vs': 2}) == Status.OFFLINE

    # Private
    assert MyFreeCams._parse_model_status({'vs': 12}) == Status.PRIVATE
    assert MyFreeCams._parse_model_status({'vs': 13}) == Status.PRIVATE
    assert MyFreeCams._parse_model_status({'vs': 91}) == Status.PRIVATE

    # Non-existent
    assert MyFreeCams._parse_model_status(None) == Status.NOTEXIST


def test_mfc_update_streamer_info():
    bot = MyFreeCams('testmodel')
    data = {
        'nm': 'testmodel',
        'vs': 0,
        'u': {'country': 'Romania', 'camserv': 1234},
        'm': {'mg': 1}
    }
    MyFreeCams._update_streamer_info(bot, data)
    assert bot.country == 'RO'
    assert bot.gender == Gender.FEMALE


def test_mfc_get_video_url(monkeypatch):
    bot = MyFreeCams('testmodel')
    bot.lastInfo = {
        'uid': 45131856,
        'u': {'camserv': 1666}
    }
    monkeypatch.setattr(MyFreeCams, 'getServerConfig', classmethod(lambda cls, force=False: {
        'wzobs_servers': {'1666': 'video966'},
        'h5video_servers': {}
    }))
    def mock_get(url, *args, **kwargs):
        if 'playlist_cmaf.m3u8' in url:
            return SimpleNamespace(status_code=404)
        return SimpleNamespace(status_code=200)
    monkeypatch.setattr(bot.session, 'get', mock_get)

    monkeypatch.setattr(bot, 'getWantedResolutionPlaylist', lambda url: f'resolved_{url}')

    url = bot.getVideoUrl()
    assert url == 'resolved_https://video966.myfreecams.com/NxServer/ngrp:mfc_a_145131856.f4v_mobile/playlist.m3u8'


def test_mfc_prefers_cmaf_playlist(monkeypatch):
    bot = MyFreeCams('testmodel')
    bot.lastInfo = {
        'uid': 45131856,
        'u': {'camserv': 1666}
    }
    monkeypatch.setattr(MyFreeCams, 'getServerConfig', classmethod(lambda cls, force=False: {
        'wzobs_servers': {},
        'h5video_servers': {'1666': 'video966'}
    }))
    monkeypatch.setattr('streamonitor.sites.myfreecams.CB_MASTER_PLAYLIST', False)

    def mock_get(url, *args, **kwargs):
        if 'playlist_cmaf.m3u8' in url:
            return SimpleNamespace(status_code=200)
        return SimpleNamespace(status_code=404)

    monkeypatch.setattr(bot.session, 'get', mock_get)

    url = bot.getVideoUrl()
    assert url == (
        'https://edgevideo.myfreecams.com/llhls/NxServer/1666/'
        'ngrp:mfc_145131856.f4v_cmaf/playlist_cmaf.m3u8'
    )


def test_mfc_rewrites_cmaf_playlist_with_separate_audio(monkeypatch):
    bot = MyFreeCams('testmodel')
    bot.headers = {}
    bot.cookies = {}
    monkeypatch.setattr('streamonitor.sites.myfreecams.CB_MASTER_PLAYLIST', True)

    master_playlist = (
        '#EXTM3U\n'
        '#EXT-X-VERSION:7\n'
        '#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio",NAME="English",'
        'DEFAULT=YES,AUTOSELECT=YES,URI="audio.m3u8"\n'
        '#EXT-X-STREAM-INF:BANDWIDTH=500000,RESOLUTION=640x360,'
        'FRAME-RATE=30,CODECS="avc1.64001f,mp4a.40.2",AUDIO="audio"\n'
        'video.m3u8\n'
    )
    monkeypatch.setattr(
        bot.session,
        'get',
        lambda url, *args, **kwargs: SimpleNamespace(
            status_code=200,
            text=master_playlist
        )
    )

    url = (
        'https://edgevideo.myfreecams.com/llhls/NxServer/1666/'
        'ngrp:mfc_145131856.f4v_cmaf/playlist_cmaf.m3u8'
    )
    result = bot._rewriteCmafPlaylist(url)

    assert isinstance(result, Path)
    assert result.suffix == '.m3u8'
    content = result.read_text(encoding='utf-8')
    assert 'TYPE=AUDIO' in content
    assert 'AUDIO="audio"' in content
    assert 'https://edgevideo.myfreecams.com/llhls/NxServer/1666/' in content

    try:
        os.unlink(result)
    except OSError:
        pass


if __name__ == '__main__':
    test_mfc_parse_status()
    print("test_mfc_parse_status passed")
    test_mfc_update_streamer_info()
    print("test_mfc_update_streamer_info passed")
    class DummyMonkeyPatch:
        def setattr(self, obj, name, val):
            setattr(obj, name, val)
    test_mfc_get_video_url(DummyMonkeyPatch())
    print("test_mfc_get_video_url passed")
    print("All tests passed!")
