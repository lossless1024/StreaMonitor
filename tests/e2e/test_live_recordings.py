"""Opt-in end-to-end tests: find a live model and record real video + audio.

Run with::

    STRMNTR_E2E=1 .venv/bin/pytest tests/e2e -v

The tests are intentionally skipped during a normal ``pytest`` run: they visit
live adult streaming sites and download a short sample for every reachable
site.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from threading import Thread

import pytest
from curl_cffi import requests as curl_requests

from streamonitor.bot import RoomIdBot
from streamonitor.downloaders.agora import AgoraStream
from streamonitor.downloaders.agora_webrtc import AgoraWebRTCBackend
from streamonitor.enums import Status
from streamonitor.sites import (
    AmateurTV,
    BongaCams,
    Cam4,
    CamsCom,
    CamSoda,
    Chaturbate,
    DreamCam,
    DreamCamVR,
    FanslyLive,
    Flirt4Free,
    ManyVids,
    MyFreeCams,
    SexChatHU,
    StreaMate,
    StripChat,
    StripChatVR,
    XLoveCam,
)

from discovery import DiscoveryError, LiveCandidate, discover

pytestmark = pytest.mark.e2e

ALL_SITE_CLASSES = [
    AmateurTV,
    BongaCams,
    Cam4,
    CamsCom,
    CamSoda,
    Chaturbate,
    DreamCam,
    DreamCamVR,
    FanslyLive,
    Flirt4Free,
    ManyVids,
    MyFreeCams,
    SexChatHU,
    StreaMate,
    StripChat,
    StripChatVR,
    XLoveCam,
]


def _selected_site_classes():
    requested = os.environ.get("STRMNTR_E2E_SITES")
    if not requested:
        return ALL_SITE_CLASSES
    wanted = {value.strip().upper() for value in requested.split(",") if value.strip()}
    return [site for site in ALL_SITE_CLASSES if site.siteslug.upper() in wanted]


SITE_CLASSES = _selected_site_classes()

_MEDIA_SUFFIXES = {".mp4", ".mkv", ".webm", ".mov", ".avi", ".wmv", ".ts"}


def _media_files(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    return [
        path
        for path in folder.rglob("*")
        if path.is_file() and path.suffix.lower() in _MEDIA_SUFFIXES
    ]


def _active_media(folder: Path) -> list[Path]:
    return [path for path in _media_files(folder) if path.stat().st_size > 1024]


def _is_connectivity_error(error: BaseException) -> bool:
    text = f"{type(error).__name__}: {error}".lower()
    markers = (
        "connection",
        "connect",
        "timed out",
        "timeout",
        "certificate",
        "ssl",
        "dns",
        "name or service not known",
        "failed to perform",
        "temporary failure",
        "network is unreachable",
    )
    if any(marker in text for marker in markers):
        return True
    exceptions = getattr(curl_requests, "exceptions", None)
    if exceptions is not None:
        for name in ("ConnectionError", "SSLError", "Timeout", "CertificateVerifyError"):
            cls = getattr(exceptions, name, None)
            if cls is not None and isinstance(error, cls):
                return True
    return False


def _instantiate(site_cls, candidate: LiveCandidate):
    if candidate.room_id and issubclass(site_cls, RoomIdBot):
        return site_cls(candidate.username, room_id=candidate.room_id)
    return site_cls(candidate.username)


def _find_public_bot(site_cls, candidates: list[LiveCandidate]):
    attempts: list[str] = []
    connectivity_errors: list[BaseException] = []
    other_errors: list[BaseException] = []
    successful_probes = 0

    for candidate in candidates[:20]:
        try:
            bot = _instantiate(site_cls, candidate)
            if bot.sc == Status.NOTEXIST:
                attempts.append(f"{candidate.username}: NOTEXIST (constructor)")
                continue
            status = bot.getStatus()
            successful_probes += 1
            attempts.append(f"{candidate.username}: {status.name}")
            if status == Status.PUBLIC:
                bot.sc = status
                return bot, attempts
        except Exception as error:  # noqa: BLE001 - status APIs fail in many ways
            attempts.append(f"{candidate.username}: {type(error).__name__}: {error}")
            if _is_connectivity_error(error):
                connectivity_errors.append(error)
            else:
                other_errors.append(error)

    if successful_probes == 0 and other_errors:
        raise AssertionError(
            f"no candidate could be probed because of non-connectivity errors: {attempts}"
        )
    if successful_probes == 0 and connectivity_errors:
        raise ConnectionError(
            f"all {len(attempts)} status attempts failed to reach the site: "
            f"{attempts[-1]}"
        )
    return None, attempts


def _stop_download(bot, thread: Thread, timeout: float = 90.0) -> bool:
    if thread.is_alive():
        stop = getattr(bot, "stopDownload", None)
        if stop:
            stop()
        thread.join(timeout)
    if thread.is_alive():
        stop = getattr(bot, "stopDownload", None)
        if stop:
            stop()
        thread.join(30.0)
    return not thread.is_alive()


def _record(bot, url, output_file: Path, seconds: int) -> str | None:
    """Record for ``seconds`` and return an error string, if any."""
    result: dict[str, object] = {}

    def run():
        try:
            result["value"] = bot.getVideo(bot, url, str(output_file))
        except BaseException as error:  # noqa: BLE001 - reported by the test
            result["error"] = error

    folder = Path(bot.outputFolder)
    thread = Thread(target=run, name=f"e2e-record-{bot.siteslug}", daemon=True)
    thread.start()

    deadline = time.monotonic() + (
        120 if isinstance(url, AgoraStream) else min(60, max(25, seconds * 2))
    )
    first_data_at = None
    while time.monotonic() < deadline:
        if _active_media(folder):
            first_data_at = time.monotonic()
            break
        if not thread.is_alive():
            break
        time.sleep(0.5)

    if first_data_at is not None:
        remaining = seconds - (time.monotonic() - first_data_at)
        if remaining > 0:
            time.sleep(remaining)
    elif thread.is_alive():
        # The recorder is alive but produced nothing within the startup
        # allowance.  Stop it anyway so the failure includes the directory.
        pass

    stopped = _stop_download(bot, thread)
    if not stopped:
        return "downloader did not stop after stopDownload()"

    error = result.get("error")
    if error is not None:
        return f"downloader raised {type(error).__name__}: {error}"
    if result.get("value") is False:
        return "getVideo() returned False"
    return None


def _probe_and_decode(path: Path, ffprobe: str, ffmpeg: str) -> dict:
    probe = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "stream=index,codec_type,codec_name,width,height,channels",
            "-show_entries",
            "format=duration,size",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=90,
    )
    if probe.returncode != 0:
        raise AssertionError(f"ffprobe failed for {path}:\n{probe.stderr[-2000:]}")
    import json

    data = json.loads(probe.stdout or "{}")
    streams = data.get("streams", [])
    video = [stream for stream in streams if stream.get("codec_type") == "video"]
    audio = [stream for stream in streams if stream.get("codec_type") == "audio"]
    if not video:
        raise AssertionError(f"no video stream in {path}: {streams}")
    if not audio:
        raise AssertionError(f"no audio stream in {path}: {streams}")

    # Reading the headers (ffprobe) is not enough: decode a few frames from
    # each stream so a container with broken payloads does not pass.
    for stream_type, frame_args in (("v", ["-frames:v", "5"]), ("a", ["-frames:a", "10"])):
        decode = subprocess.run(
            [
                ffmpeg,
                "-v",
                "error",
                "-i",
                str(path),
                "-map",
                f"0:{stream_type}:0",
                *frame_args,
                "-f",
                "null",
                "-",
            ],
            capture_output=True,
            text=True,
            timeout=90,
        )
        if decode.returncode != 0:
            raise AssertionError(
                f"ffmpeg could not decode the {stream_type} stream in {path}:\n"
                f"{decode.stderr[-2000:]}"
            )

    return {
        "video": video[0],
        "audio": audio[0],
        "format": data.get("format", {}),
        "size": path.stat().st_size,
    }


@pytest.mark.parametrize(
    "site_cls", SITE_CLASSES, ids=[site.siteslug for site in SITE_CLASSES]
)
def test_live_site_records_video_and_audio(
    site_cls,
    download_root,
    ffmpeg_bin,
    ffprobe_bin,
    record_seconds,
):
    try:
        candidates, note = discover(site_cls.siteslug)
    except DiscoveryError as error:
        pytest.skip(str(error))
    except Exception as error:  # noqa: BLE001 - a changed discovery endpoint
        if _is_connectivity_error(error):
            pytest.skip(f"{site_cls.siteslug} is unreachable during discovery: {error}")
        raise

    if not candidates:
        reason = note or "discovery returned no live candidates"
        pytest.skip(f"no live {site_cls.site} model found: {reason}")

    try:
        bot, attempts = _find_public_bot(site_cls, candidates)
    except ConnectionError as error:
        pytest.skip(str(error))

    if bot is None:
        pytest.skip(
            f"no public {site_cls.site} model among {len(attempts)} candidates: "
            + "; ".join(attempts[:8])
        )

    assert bot.sc == Status.PUBLIC, f"expected PUBLIC, got {bot.sc}"
    url = bot.getVideoUrl()
    assert url is not None, f"{site_cls.siteslug}/{bot.username} returned no video URL"
    if isinstance(url, AgoraStream) and not AgoraWebRTCBackend.available():
        pytest.skip(
            "the Agora WebRTC recorder dependencies are missing; install "
            "requirements.txt (or use the Docker image)"
        )

    output_file = Path(bot.genOutFilename())
    folder = Path(bot.outputFolder)
    print(
        f"\n[e2e] {site_cls.siteslug}/{bot.username}: recording {url!s} "
        f"for ~{record_seconds}s into {folder}"
    )

    error = _record(bot, url, output_file, record_seconds)
    media = _media_files(folder)
    if error:
        raise AssertionError(
            f"{site_cls.siteslug}/{bot.username}: {error}; files={media}"
        )
    if not media:
        raise AssertionError(
            f"{site_cls.siteslug}/{bot.username}: recording produced no media files "
            f"in {folder}"
        )

    # The largest file is the completed recording (native-HLS and websocket
    # downloaders leave intermediate files behind only on failure).
    path = max(media, key=lambda item: item.stat().st_size)
    if path.stat().st_size < 4096:
        raise AssertionError(
            f"{site_cls.siteslug}/{bot.username}: recording is only "
            f"{path.stat().st_size} bytes: {path}"
        )

    details = _probe_and_decode(path, ffprobe_bin, ffmpeg_bin)
    raw_duration = details["format"].get("duration")
    duration = float(raw_duration) if raw_duration not in (None, "N/A") else 0.0
    minimum = max(2.0, record_seconds * 0.5)
    assert duration >= minimum, (
        f"{site_cls.siteslug}/{bot.username}: recording is only {duration:.2f}s "
        f"(expected at least {minimum:.1f}s); files={media}"
    )
    print(
        f"[e2e] {site_cls.siteslug}/{bot.username}: "
        f"{path.name} ({details['size']} bytes, "
        f"{details['format'].get('duration', '?')}s) "
        f"video={details['video'].get('codec_name')} "
        f"{details['video'].get('width')}x{details['video'].get('height')} "
        f"audio={details['audio'].get('codec_name')} "
        f"channels={details['audio'].get('channels')}"
    )
