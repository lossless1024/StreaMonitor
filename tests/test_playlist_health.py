import logging
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from streamonitor.utils.playlist_health import inspect_and_report, inspect_playlist
from streamonitor.sites.stripchat import StripChat
from streamonitor.bot import Bot
import streamonitor.downloaders.hls as hls_module


def test_playlist_health_accepts_separate_audio_master():
    content = (
        "#EXTM3U\n"
        "#EXT-X-VERSION:7\n"
        '#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio",NAME="English",'
        "DEFAULT=YES,AUTOSELECT=YES,URI=\"audio.m3u8\"\n"
        '#EXT-X-STREAM-INF:BANDWIDTH=500000,RESOLUTION=640x360,AUDIO="audio"\n'
        "video.m3u8\n"
    )

    health = inspect_playlist(content, "https://example.com/master.m3u8")

    assert health.is_variant
    assert health.variant_count == 1
    assert health.audio_rendition_count == 1


@pytest.mark.parametrize(
    "content, message",
    [
        ("", "not an HLS playlist"),
        ("#EXTM3U\n#EXT-X-ENDLIST\n", "no media segments"),
    ],
)
def test_playlist_health_rejects_invalid_or_changed_formats(content, message):
    with pytest.raises(ValueError, match=message):
        inspect_playlist(content, "https://example.com/master.m3u8")


def test_playlist_health_accepts_legacy_master_with_integrated_audio():
    content = (
        "#EXTM3U\n"
        '#EXT-X-STREAM-INF:BANDWIDTH=500000,RESOLUTION=640x360\n'
        "video.m3u8\n"
    )

    health = inspect_playlist(content, "https://example.com/NxServer/playlist.m3u8")

    assert health.is_variant
    assert health.audio_rendition_count == 0


def test_playlist_health_rejects_cmaf_master_without_audio():
    content = (
        "#EXTM3U\n"
        '#EXT-X-STREAM-INF:BANDWIDTH=500000,RESOLUTION=640x360\n'
        "video.m3u8\n"
    )

    with pytest.raises(ValueError, match="no usable audio rendition"):
        inspect_playlist(
            content,
            "https://example.com/llhls/NxServer/playlist_cmaf.m3u8",
        )


def test_get_wanted_playlist_accepts_resolved_media_playlist():
    bot = object.__new__(Bot)
    bot.siteslug = 'MFC'
    bot.headers = {}
    bot.cookies = {}
    bot.logger = logging.getLogger("playlist-resolution-test")

    master = (
        "#EXTM3U\n"
        "#EXT-X-VERSION:3\n"
        "#EXT-X-STREAM-INF:BANDWIDTH=500000,RESOLUTION=640x360\n"
        "video.m3u8\n"
    )
    media = (
        "#EXTM3U\n"
        "#EXT-X-VERSION:3\n"
        "#EXT-X-TARGETDURATION:4\n"
        "#EXTINF:4,\n"
        "segment0.ts\n"
    )

    class MockSession:
        def get(self, url, **kwargs):
            if url.endswith('/master.m3u8'):
                return SimpleNamespace(status_code=200, text=master)
            if url.endswith('/video.m3u8'):
                return SimpleNamespace(status_code=200, text=media)
            return SimpleNamespace(status_code=404, text='')

    bot.session = MockSession()

    selected = bot.getWantedResolutionPlaylist(
        "https://example.com/master.m3u8"
    )

    assert selected == "https://example.com/video.m3u8"


def test_get_wanted_playlist_rejects_unavailable_media_playlist():
    bot = object.__new__(Bot)
    bot.siteslug = 'MFC'
    bot.headers = {}
    bot.cookies = {}
    bot.logger = logging.getLogger("playlist-resolution-test")

    master = (
        "#EXTM3U\n"
        "#EXT-X-VERSION:3\n"
        "#EXT-X-STREAM-INF:BANDWIDTH=500000,RESOLUTION=640x360\n"
        "video.m3u8\n"
    )

    class MockSession:
        def get(self, url, **kwargs):
            if url.endswith('/master.m3u8'):
                return SimpleNamespace(status_code=200, text=master)
            return SimpleNamespace(status_code=404, text='')

    bot.session = MockSession()

    selected = bot.getWantedResolutionPlaylist(
        "https://example.com/master.m3u8"
    )

    assert selected is None


def test_playlist_health_reports_warning_without_raising():
    logger = logging.getLogger("playlist-health-test")

    health = inspect_and_report(
        logger,
        "MFC",
        "https://example.com/master.m3u8",
        "not a playlist",
    )

    assert health is None


def test_playlist_health_detects_stripchat_mouflon_marker():
    content = (
        "#EXTM3U\n"
        "#EXT-X-MOUFLON:PROGRAM:pkey\n"
        "#EXTINF:2,\n"
        "media.mp4\n"
        "#EXT-X-ENDLIST\n"
    )

    health = inspect_and_report(
        logging.getLogger("playlist-health-test"),
        "SC",
        "https://edge-hls.example/hls/master.m3u8",
        content,
    )

    assert health is not None
    assert health.has_mouflon_marker


def test_stripchat_extracts_remote_key_map():
    content = json.dumps({
        '1Dzcc6OjP73LKbtI': 'Y64UVwX5RrIWnOLp',
        '7uUnbD0jMCB9GH32': 'lzCQ6QBTnLpB0zMF',
    })

    discovered = StripChat._extractMouflonKeys(content)

    assert discovered == {
        '1Dzcc6OjP73LKbtI': 'Y64UVwX5RrIWnOLp',
        '7uUnbD0jMCB9GH32': 'lzCQ6QBTnLpB0zMF',
    }


def test_stripchat_extracts_and_persists_mouflon_key(monkeypatch, tmp_path):
    cache = tmp_path / 'stripchat_mouflon_keys.json'
    monkeypatch.setattr(StripChat, '_mouflon_cache_filename', str(cache))
    monkeypatch.setattr(StripChat, '_mouflon_meta_filename', str(cache) + '.meta.json')
    monkeypatch.setattr(StripChat, '_mouflon_keys', {})
    monkeypatch.setattr(StripChat, '_cached_keys', None)
    monkeypatch.setattr(StripChat, '_mouflon_last_refresh', 123.0)

    discovered = StripChat._extractMouflonKeys(
        json.dumps({
            'mouflon': {
                'pkey': 'test-pkey',
                'pdkey': 'test-decryption-key',
            }
        })
    )
    StripChat._mouflon_keys.update(discovered)
    StripChat._saveMouflonKeys()

    assert json.loads(cache.read_text()) == {
        'test-pkey': 'test-decryption-key',
    }
    assert json.loads((tmp_path / 'stripchat_mouflon_keys.json.meta.json').read_text())[
        'refreshed_at'
    ] == 123.0


def test_stripchat_m3u_marker_resolves_cached_key(monkeypatch):
    monkeypatch.setattr(
        StripChat,
        '_mouflon_keys',
        {'pkey123': 'decryption-key'},
    )
    monkeypatch.setattr(StripChat, '_cached_keys', None)

    psch, pkey, pdkey = StripChat._getMouflonFromM3U(
        '#EXT-X-MOUFLON:PROGRAM:v2:pkey123\n'
    )

    assert psch == 'v2'
    assert pkey == 'pkey123'
    assert pdkey == 'decryption-key'


def test_stripchat_real_mouflon_marker_is_parsed_without_cached_key(monkeypatch):
    monkeypatch.setattr(StripChat, '_mouflon_keys', {})
    monkeypatch.setattr(StripChat, '_mouflon_refresh_thread', None)
    monkeypatch.setattr(StripChat, '_mouflon_last_refresh', 0)

    psch, pkey, pdkey = StripChat._getMouflonFromM3U(
        '#EXT-X-MOUFLON:PSCH:v2:1Dzcc6OjP73LKbtI\n'
    )

    assert psch == 'v2'
    assert pkey == '1Dzcc6OjP73LKbtI'
    assert pdkey is None


def test_stripchat_collects_all_working_pkey_choices(monkeypatch):
    monkeypatch.setattr(
        StripChat,
        '_mouflon_keys',
        {
            'pkey-first': 'pdkey-first',
            'pkey-second': 'pdkey-second',
        },
    )

    choices = StripChat._getMouflonChoices(
        "#EXTM3U\n"
        "#EXT-X-MOUFLON:PSCH:v2:pkey-first\n"
        "#EXT-X-MOUFLON:PSCH:v2:pkey-second\n"
    )

    assert choices == [
        ('v2', 'pkey-first', 'pdkey-first'),
        ('v2', 'pkey-second', 'pdkey-second'),
    ]


def test_stripchat_decoder_rejects_playlist_when_key_is_pending(monkeypatch):
    monkeypatch.setattr(StripChat, '_mouflon_keys', {})
    content = (
        "#EXTM3U\n"
        "#EXT-X-MOUFLON:PSCH:v2:1Dzcc6OjP73LKbtI\n"
        "#EXT-X-TARGETDURATION:2\n"
    )

    assert StripChat.m3u_decoder(content) is None


def test_stripchat_get_playlist_variants_pauses_without_pdkey(monkeypatch):
    bot = object.__new__(StripChat)
    bot.room_id = '264843443'
    bot.vr = False
    bot.headers = {}
    bot.cookies = {}
    bot.logger = logging.getLogger("stripchat-playlist-test")
    bot.debug = lambda *args, **kwargs: None
    bot.log = lambda *args, **kwargs: None
    bot.session = SimpleNamespace(
        get=lambda *args, **kwargs: SimpleNamespace(
            status_code=200,
            content=(
                b"#EXTM3U\n"
                b"#EXT-X-MOUFLON:PSCH:v2:1Dzcc6OjP73LKbtI\n"
                b"#EXT-X-STREAM-INF:BANDWIDTH=500000,RESOLUTION=360x480\n"
                b"video.m3u8\n"
            ),
        )
    )
    monkeypatch.setattr(StripChat, '_mouflon_keys', {})
    monkeypatch.setattr(StripChat, '_mouflon_last_refresh', 0)
    monkeypatch.setattr(StripChat, '_mouflon_refresh_thread', None)

    assert bot.getPlaylistVariants(None) == []


def test_native_hls_creates_output_directory_before_writing(tmp_path, monkeypatch):
    class MockSession:
        def get(self, *args, **kwargs):
            return SimpleNamespace(
                status_code=200,
                content=b"#EXTM3U\n#EXT-X-TARGETDURATION:2\n",
            )

    monkeypatch.setattr(hls_module.requests, 'Session', MockSession)
    bot = SimpleNamespace(
        stopDownloadFlag=False,
        headers={},
        cookies={},
        logger=logging.getLogger("native-hls-test"),
        debug=lambda *args: None,
    )
    output_dir = tmp_path / 'missing-output'
    filename = str(output_dir / 'model-20261121-140000.mkv')

    result = hls_module.getVideoNativeHLS(
        bot,
        'https://example.com/master.m3u8',
        filename,
    )

    assert result is False
    assert output_dir.is_dir()


def test_stripchat_missing_key_schedules_async_refresh(monkeypatch):
    started = {}

    class FakeThread:
        def __init__(self, target, kwargs, name, daemon):
            started['target'] = target
            started['kwargs'] = kwargs
            started['name'] = name
            started['daemon'] = daemon

        def start(self):
            started['started'] = True

        def is_alive(self):
            return False

    monkeypatch.setattr(StripChat, '_mouflon_keys', {})
    monkeypatch.setattr(StripChat, '_mouflon_last_refresh', 0)
    monkeypatch.setattr(StripChat, '_mouflon_refresh_thread', None)
    monkeypatch.setattr(
        'streamonitor.sites.stripchat.threading.Thread',
        FakeThread,
    )

    assert StripChat.getMouflonDecKey('unknown-key') is None
    assert started['started'] is True
    assert started['daemon'] is True
    assert started['name'] == 'stripchat-mouflon-refresh'
