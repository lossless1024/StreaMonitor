import os
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from streamonitor.sites.chaturbate import Chaturbate

# Ensure the master playlist rewrite is enabled for the test
from parameters import CB_MASTER_PLAYLIST

@pytest.fixture(autouse=True)
def enable_master_playlist(monkeypatch):
    # Force the flag to True even if the default changes
    monkeypatch.setattr('parameters.CB_MASTER_PLAYLIST', True, raising=False)

def test_chaturbate_hls_master_rewrite(monkeypatch):
    """Verify that a standard HLS master playlist is rewritten to include audio.

    The test mocks the HTTP request for the master playlist and checks that the
    returned value is a local ``.m3u8`` file (Path) containing both audio and
    video entries.
    """
    # Minimal HLS master playlist with separate audio and video renditions
    master_playlist = (
        "#EXTM3U\n"
        "#EXT-X-VERSION:3\n"
        '#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="aud1",NAME="English",DEFAULT=YES,AUTOSELECT=YES,FORCED=NO,URI="audio.m3u8"\n'
        '#EXT-X-STREAM-INF:BANDWIDTH=500000,RESOLUTION=640x360,FRAME-RATE=30,CODECS="avc1.64001f,mp4a.40.2",AUDIO="aud1"\n'
        "video.m3u8\n"
    )

    # Mock response object
    mock_response = SimpleNamespace(
        status_code=200,
        text=master_playlist,
        content=master_playlist.encode('utf-8')
    )

    # Mock session.get to return our mock response regardless of URL
    class MockSession:
        def get(self, *args, **kwargs):
            return mock_response

    # Create a Chaturbate instance with a dummy username
    cb = Chaturbate('dummy_user')
    # Replace the internal session with the mock session
    cb.session = MockSession()
    # Ensure headers and cookies exist (they are accessed but not used in the mock)
    cb.headers = {}
    cb.cookies = {}
    # Set lastInfo to contain a master playlist URL
    cb.lastInfo = {'url': 'http://example.com/master.m3u8'}

    # Call the method under test
    result = cb.getVideoUrl()

    # The result should be a Path pointing to a temporary .m3u8 file
    assert isinstance(result, Path)
    assert result.suffix == '.m3u8'
    # Verify the file exists and contains the rewritten playlist
    with open(result, 'r', encoding='utf-8') as f:
        content = f.read()
    assert '#EXT-X-MEDIA' in content
    assert 'TYPE=AUDIO' in content
    assert 'AUDIO="aud1"' in content or 'AUDIO="aud1"' in content

    # Cleanup the temporary file
    try:
        os.unlink(result)
    except OSError:
        pass
