"""Unit tests for the Agora downloader core."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import threading
import time

import pytest

import parameters
from streamonitor.downloaders import agora
from streamonitor.downloaders.agora import (
    AgoraCredentials,
    AgoraDownloader,
    AgoraStream,
)
from streamonitor.downloaders.agora_webrtc import AgoraBackendUnavailable


class FakeBot:
    def __init__(self):
        self.logger = logging.getLogger("test-agora")
        self.stopDownload = None
        self.filename_extra_suffix = ""


class FakeBackend:
    def __init__(self, events=None, write_media=True, block=False,
                 start_error=None):
        self.events = list(events or [])
        self.write_media = write_media
        self.block = block
        self.start_error = start_error
        self.reported_file = None
        self.media = None
        self.exit_code = None
        self.stop_requested = threading.Event()
        self.started_with = None
        self.renewed = []
        self.closed = False
        self._finished = False

    def start(self, credentials, output, preferred_stream="high", max_duration=0):
        if self.start_error:
            raise self.start_error
        self.started_with = (credentials, output, preferred_stream, max_duration)
        self.reported_file = output
        if self.write_media:
            with open(output, "wb") as media_file:
                media_file.write(b"\0" * 2048)

    def next_event(self, timeout=0.5):
        if self.events:
            return self.events.pop(0)
        if self.block and not self.stop_requested.is_set():
            self.stop_requested.wait(timeout)
            return None
        if not self._finished:
            self._finished = True
            return {"event": "stopped", "file": self.reported_file}
        return None

    @property
    def exited(self):
        return self._finished

    def request_stop(self):
        self.stop_requested.set()

    def renew_token(self, token):
        self.renewed.append(token)
        return True

    def close(self, timeout=15):
        self.closed = True
        return 0


def make_stream(token="SECRET", uid=42, expires_at=None, refresh=None):
    return AgoraStream(
        credentials=AgoraCredentials(
            app_id="app-id", channel="channel-name", token=token, uid=uid,
            expires_at=expires_at,
        ),
        refresh=refresh,
        label="Test/stream",
    )


def test_stream_never_exposes_the_token():
    stream = make_stream()
    assert "SECRET" not in str(stream)
    assert "SECRET" not in repr(stream)
    assert "SECRET" not in str(stream.credentials)
    assert "SECRET" not in repr(stream.credentials)
    assert "channel-name" in str(stream)
    assert "42" in str(stream)


def test_part_filename_and_temp_filename():
    assert agora._part_filename("/tmp/user-1.mp4", 1) == "/tmp/user-1.mp4"
    assert agora._part_filename("/tmp/user-1.mp4", 2) == "/tmp/user-1_part2.mp4"
    assert agora._temp_filename("/tmp/user-1.mp4").endswith(".agora.mp4")


def test_record_logs_do_not_contain_the_token(tmp_path, monkeypatch):
    import io

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    logger = logging.getLogger("test-agora-redaction")
    logger.handlers = [handler]
    logger.setLevel(logging.DEBUG)

    bot = FakeBot()
    bot.logger = logger
    backend = FakeBackend(events=[{"event": "joined"}, {"event": "media",
                                                         "width": 640,
                                                         "height": 360}],
                          block=True)
    downloader = AgoraDownloader(bot, make_stream(), backend=backend)
    monkeypatch.setattr(agora, "finalize_recording",
                        lambda source, filename, logger=None, suffix="": True)

    thread = threading.Thread(target=lambda: downloader.record(str(tmp_path / "out.mp4")))
    thread.start()
    time.sleep(0.2)
    downloader.stop()
    thread.join(5)

    assert "SECRET" not in stream.getvalue()


def test_record_stops_cleanly_and_removes_the_temp_file(tmp_path, monkeypatch):
    backend = FakeBackend(events=[{"event": "joined"}, {"event": "media",
                                                         "width": 1280,
                                                         "height": 720}],
                          block=True)
    bot = FakeBot()
    downloader = AgoraDownloader(bot, make_stream(), backend=backend)
    result = []

    finalized = {}

    def fake_finalize(source, filename, logger=None, suffix=""):
        finalized["source"] = source
        finalized["filename"] = filename
        os.unlink(source)
        return True

    monkeypatch.setattr(agora, "finalize_recording", fake_finalize)

    thread = threading.Thread(target=lambda: result.append(downloader.record(str(tmp_path / "out.mp4"))))
    thread.start()
    time.sleep(0.2)
    assert bot.stopDownload is not None
    downloader.stop()
    downloader.stop()  # idempotent
    thread.join(5)

    assert not thread.is_alive()
    assert result == [True]
    assert backend.closed
    assert finalized["filename"] == str(tmp_path / "out.mp4")
    assert not os.path.exists(finalized["source"])
    assert bot.stopDownload is None


def test_record_without_media_returns_false(tmp_path, monkeypatch):
    backend = FakeBackend(events=[{"event": "joined"}], write_media=False)
    bot = FakeBot()
    downloader = AgoraDownloader(bot, make_stream(), backend=backend)
    called = []
    monkeypatch.setattr(
        agora, "finalize_recording",
        lambda *args, **kwargs: called.append(args) or True,
    )

    assert downloader.record(str(tmp_path / "out.mp4")) is False
    assert called == []
    assert bot.stopDownload is None


def test_unavailable_backend_returns_false(tmp_path):
    backend = FakeBackend(start_error=AgoraBackendUnavailable("missing jar"))
    bot = FakeBot()
    downloader = AgoraDownloader(bot, make_stream(), backend=backend)
    assert downloader.record(str(tmp_path / "out.mp4")) is False
    assert bot.stopDownload is None


def test_incomplete_credentials_do_not_start(tmp_path):
    backend = FakeBackend()
    bot = FakeBot()
    stream = make_stream()
    stream.credentials = AgoraCredentials("app", "", "token", 1)
    downloader = AgoraDownloader(bot, stream, backend=backend)
    assert downloader.record(str(tmp_path / "out.mp4")) is False
    assert backend.started_with is None


def test_unsupported_backend_does_not_start(tmp_path, monkeypatch):
    backend = FakeBackend()
    bot = FakeBot()
    monkeypatch.setattr(parameters, "AGORA_BACKEND", "native")
    downloader = AgoraDownloader(bot, make_stream(), backend=backend)
    assert downloader.record(str(tmp_path / "out.mp4")) is False
    assert backend.started_with is None


def test_token_refresh_in_place(tmp_path, monkeypatch):
    refreshed = AgoraCredentials("app-id", "channel-name", "NEW", 42,
                                 expires_at=time.time() + 3600)
    backend = FakeBackend(events=[{"event": "joined"}, {"event": "media",
                                                         "width": 640,
                                                         "height": 360}],
                          block=True)
    bot = FakeBot()
    downloader = AgoraDownloader(
        bot,
        make_stream(expires_at=time.time() + 1, refresh=lambda: refreshed),
        backend=backend,
    )
    result = []

    monkeypatch.setattr(agora, "finalize_recording",
                        lambda source, filename, logger=None, suffix="": True)
    monkeypatch.setattr(parameters, "AGORA_TOKEN_REFRESH_MARGIN", 5)
    monkeypatch.setattr(parameters, "AGORA_JOIN_TIMEOUT", 1)

    thread = threading.Thread(target=lambda: result.append(downloader.record(str(tmp_path / "out.mp4"))))
    thread.start()
    time.sleep(0.4)
    downloader.stop()
    thread.join(5)

    assert result == [True]
    assert backend.renewed == ["NEW"]


@pytest.mark.skipif(shutil.which(parameters.FFMPEG_PATH) is None,
                    reason="ffmpeg is required for finalization tests")
def test_finalize_remuxes_and_segments(tmp_path, monkeypatch):
    sample = tmp_path / "sample.mp4"
    subprocess.run(
        [
            parameters.FFMPEG_PATH, "-y", "-v", "error",
            "-f", "lavfi", "-i", "testsrc=size=320x240:rate=10",
            "-f", "lavfi", "-i", "sine=frequency=440",
            "-t", "1",
            "-c:v", "mpeg4", "-c:a", "aac",
            str(sample),
        ],
        check=True,
    )

    output = tmp_path / "recording.mp4"
    source = tmp_path / "source.mp4"
    shutil.copy(sample, source)
    assert agora.finalize_recording(str(source), str(output))
    assert output.is_file() and output.stat().st_size > 0
    assert not source.exists()

    monkeypatch.setattr(parameters, "SEGMENT_TIME", "1")
    source = tmp_path / "source2.mp4"
    shutil.copy(sample, source)
    output = tmp_path / "segmented.mp4"
    assert agora.finalize_recording(str(source), str(output))
    assert list(tmp_path.glob("segmented-*.mp4"))
    assert not source.exists()

    original_container = agora.CONTAINER
    monkeypatch.setattr(parameters, "SEGMENT_TIME", None)
    try:
        agora.CONTAINER = "mkv"
        source = tmp_path / "source3.mp4"
        shutil.copy(sample, source)
        output = tmp_path / "remuxed.mkv"
        assert agora.finalize_recording(str(source), str(output))
        assert output.is_file() and output.stat().st_size > 0
        assert not source.exists()
    finally:
        agora.CONTAINER = original_container


def test_finalize_rejects_a_header_only_output(tmp_path, monkeypatch):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x" * 214)
    output = tmp_path / "out.mp4"

    class Result:
        returncode = 0

    def fake_run(command, **kwargs):
        # Simulate ffmpeg writing only an MP4 header.
        with open(command[-1], "wb") as produced:
            produced.write(b"x" * 214)
        return Result()

    monkeypatch.setattr(agora.subprocess, "run", fake_run)
    assert agora.finalize_recording(str(source), str(output)) is False
    assert source.exists()


def test_finalize_rejects_an_empty_source(tmp_path):
    source = tmp_path / "empty.mp4"
    source.write_bytes(b"")
    assert agora.finalize_recording(str(source), str(tmp_path / "out.mp4")) is False
    assert source.exists()


class FakeProcess:
    def __init__(self):
        import io
        self.stdin = io.StringIO()
        self.stdout = io.StringIO("")
        self.stderr = io.StringIO("")
        self.returncode = 0
        self.command = None

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        return self.returncode

    def terminate(self):
        self.returncode = -15

    def kill(self):
        self.returncode = -9


def test_webrtc_backend_writes_a_private_config(tmp_path, monkeypatch):
    import json
    from streamonitor.downloaders import agora_webrtc

    process = FakeProcess()

    def fake_popen(command, **kwargs):
        process.command = command
        return process

    monkeypatch.setattr(agora_webrtc.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(
        agora_webrtc.AgoraWebRTCBackend, "available",
        classmethod(lambda cls: True),
    )
    monkeypatch.setattr(agora_webrtc.AgoraWebRTCBackend, "_read_stdout", lambda self: None)
    monkeypatch.setattr(agora_webrtc.AgoraWebRTCBackend, "_read_stderr", lambda self: None)
    backend = agora_webrtc.AgoraWebRTCBackend()
    backend.start(make_stream().credentials, str(tmp_path / "out.agora.mp4"),
                  preferred_stream="low", max_duration=30)

    assert backend._config_path is not None
    assert oct(os.stat(backend._config_path).st_mode & 0o777) == "0o600"
    with open(backend._config_path) as config_file:
        config = json.load(config_file)
    assert config["streamType"] == "low"
    assert config["maxDurationSec"] == 30
    assert config["token"] == "SECRET"
    assert any("agora_worker" in part for part in process.command)
    assert "--config" in process.command

    config_path = backend._config_path
    backend.close(1)
    assert not os.path.exists(config_path)


def test_webrtc_backend_is_unavailable_without_dependencies(monkeypatch):
    from streamonitor.downloaders import agora_webrtc

    monkeypatch.setattr(agora_webrtc, "_REQUIRED_MODULES", ("definitely-missing",))
    assert agora_webrtc.AgoraWebRTCBackend.available() is False
    assert agora_webrtc.AgoraWebRTCBackend.worker_path().endswith("agora_worker.py")


def test_webrtc_backend_redacts_the_token_from_stderr():
    from streamonitor.downloaders import agora_webrtc

    backend = agora_webrtc.AgoraWebRTCBackend()
    backend._token = "SECRET"
    assert "SECRET" not in backend._redact("join token SECRET and more")
    assert "<redacted>" in backend._redact("join token SECRET and more")


_OFFER_SDP = """v=0
o=- 1 2 IN IP4 127.0.0.1
s=-
t=0 0
a=group:BUNDLE 0 1
m=audio 9 UDP/TLS/RTP/SAVPF 111
c=IN IP4 0.0.0.0
a=mid:0
a=ice-ufrag:localufrag
a=ice-pwd:localpwd
a=fingerprint:sha-256 AA:BB
a=setup:actpass
a=rtpmap:111 opus/48000/2
a=rtcp-fb:111 transport-cc
m=video 9 UDP/TLS/RTP/SAVPF 96
c=IN IP4 0.0.0.0
a=mid:1
a=ice-ufrag:localufrag
a=ice-pwd:localpwd
a=fingerprint:sha-256 AA:BB
a=setup:actpass
a=rtpmap:96 VP8/90000
a=rtcp-fb:96 nack
a=rtcp-fb:96 nack pli
"""


def test_parse_media_sections_reads_ice_and_codecs():
    from streamonitor.downloaders.agora_worker import _parse_media_sections

    sections = _parse_media_sections(_OFFER_SDP)
    assert [section["kind"] for section in sections] == ["audio", "video"]
    assert sections[0]["mid"] == "0"
    assert sections[0]["ufrag"] == "localufrag"
    assert sections[0]["pwd"] == "localpwd"
    assert sections[0]["fingerprint"] == "sha-256 AA:BB"
    assert sections[0]["codecs"][111]["name"] == "opus"
    assert sections[0]["codecs"][111]["channels"] == 2
    assert sections[1]["codecs"][96]["name"] == "VP8"
    assert sections[1]["codecs"][96]["fb"] == ["nack", "nack pli"]


def test_build_answer_sdp_uses_the_server_ice_and_codecs():
    from streamonitor.downloaders.agora_worker import _build_answer_sdp

    server_ortc = {
        "iceParameters": {
            "iceUfrag": "serverufrag",
            "icePwd": "serverpwd",
            "candidates": [{
                "foundation": "1",
                "protocol": "udp",
                "priority": 1,
                "ip": "192.0.2.10",
                "port": 4443,
                "type": "host",
            }],
        },
        "dtlsParameters": {
            "role": "server",
            "fingerprints": [{"algorithm": "sha-256", "fingerprint": "CC:DD"}],
        },
        "rtpCapabilities": {"sendrecv": {
            "audioCodecs": [{
                "payloadType": 111,
                "rtpMap": {
                    "encodingName": "opus", "clockRate": 48000,
                    "encodingParameters": 2,
                },
                "rtcpFeedbacks": [{"type": "transport-cc"}],
            }],
            "videoCodecs": [{
                "payloadType": 96,
                "rtpMap": {"encodingName": "VP8", "clockRate": 90000},
                "rtcpFeedbacks": [{"type": "nack"}, {"type": "nack", "parameter": "pli"}],
            }],
        }},
    }

    answer = _build_answer_sdp(_OFFER_SDP, server_ortc)
    assert "m=audio 9 UDP/TLS/RTP/SAVPF 111" in answer
    assert "m=video 9 UDP/TLS/RTP/SAVPF 96" in answer
    assert "a=ice-ufrag:serverufrag" in answer
    assert "a=ice-pwd:serverpwd" in answer
    assert "a=fingerprint:sha-256 CC:DD" in answer
    assert "a=setup:passive" in answer
    assert "a=candidate:1 1 udp 1 192.0.2.10 4443 typ host" in answer
    assert "a=sendonly" in answer
    assert "a=rtpmap:111 opus/48000/2" in answer
    assert "a=rtpmap:96 VP8/90000" in answer
