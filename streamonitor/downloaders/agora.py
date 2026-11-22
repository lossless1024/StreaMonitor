"""Agora livestream downloader.

Agora is an RTC/SFU platform: there is no HLS playlist to hand to ffmpeg.  A
site class obtains an :class:`AgoraStream` (App ID, channel, token, uid) and
this module joins the channel with the Python WebRTC worker, writes a
temporary MP4 and remuxes it into the user's container afterwards.  ManyVids
publishes VP8/Opus, so the worker decodes those and re-encodes H.264/AAC.

The token is never logged.  ``AgoraStream`` and ``AgoraCredentials`` deliberately
print only the label, channel and uid.
"""

from __future__ import annotations

import glob
import os
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

import parameters
from parameters import CONTAINER, DEBUG, FFMPEG_PATH
from streamonitor.bot import Bot
from streamonitor.downloaders.agora_webrtc import AgoraBackendUnavailable, AgoraWebRTCBackend

# A valid MP4 has at least a moov atom and a few frames.  This rejects the
# header-only file the recorder leaves when the muxer could not open a stream.
_MIN_PLAYABLE_SIZE = 1024


@dataclass(frozen=True)
class AgoraCredentials:
    app_id: str
    channel: str
    token: str | None
    uid: int | str
    expires_at: float | None = None

    def __str__(self) -> str:
        return f"AgoraCredentials(channel={self.channel} uid={self.uid})"

    def __repr__(self) -> str:
        return self.__str__()


@dataclass
class AgoraStream:
    credentials: AgoraCredentials
    refresh: Optional[Callable[[], AgoraCredentials]] = None
    referer: str | None = None
    user_agent: str | None = None
    label: str = "Agora"
    preferred_stream: str = "high"  # "high" | "low"

    def __str__(self) -> str:
        # Never include the token in logs, the web UI, or test output.
        return (
            f"{self.label} channel={self.credentials.channel} "
            f"uid={self.credentials.uid}"
        )

    def __repr__(self) -> str:
        return self.__str__()


def _part_filename(filename: str, part: int) -> str:
    if part <= 1:
        return filename
    base, extension = os.path.splitext(filename)
    return f"{base}_part{part}{extension}"


def _temp_filename(filename: str) -> str:
    base = os.path.splitext(filename)[0]
    temp = base + ".agora.mp4"
    if os.path.exists(temp):
        temp = base + f".agora-{int(time.time())}.mp4"
    return temp


def _segment_prefix(filename: str, suffix: str = "") -> tuple[str, str]:
    """Return the output folder and the segment pattern's name prefix."""
    folder = os.path.dirname(os.path.abspath(filename))
    stem = os.path.splitext(os.path.basename(filename))[0]
    parts = stem.rsplit("-", maxsplit=2)
    if len(parts) == 3 and len(parts[1]) == 8 and parts[2][:6].isdigit():
        username = parts[0]
    else:
        username = stem
    return folder, f"{username}-%Y%m%d-%H%M%S{suffix}.{CONTAINER}"


def finalize_recording(source: str, filename: str, logger=None,
                       suffix: str = "") -> bool:
    """Remux a recorder file into the configured container.

    Returns ``True`` only when ffmpeg produced at least one non-empty output
    file.  The source is removed on success.
    """
    if not source or not os.path.isfile(source) or os.path.getsize(source) <= 0:
        if logger is not None:
            logger.warning("Agora recording produced no media")
        return False

    os.makedirs(os.path.dirname(os.path.abspath(filename)), exist_ok=True)
    folder, segment_pattern = _segment_prefix(filename, suffix)
    container = CONTAINER
    cmd = [FFMPEG_PATH, "-y", "-i", source, "-c", "copy"]

    before: set[str] = set()
    if parameters.SEGMENT_TIME is not None:
        before = set(glob.glob(os.path.join(folder, f"*{suffix}.{container}")))
        cmd.extend([
            "-f", "segment",
            "-reset_timestamps", "1",
            "-segment_time", str(parameters.SEGMENT_TIME),
            "-strftime", "1",
            os.path.join(folder, segment_pattern),
        ])
        output_path = None
    else:
        output_path = os.path.splitext(filename)[0] + "." + container
        cmd.append(output_path)

    stdout = open(filename + ".postprocess_stdout.log", "w+") if DEBUG else subprocess.DEVNULL
    stderr = open(filename + ".postprocess_stderr.log", "w+") if DEBUG else subprocess.DEVNULL
    try:
        result = subprocess.run(cmd, stdout=stdout, stderr=stderr)
    except OSError as error:
        if logger is not None:
            logger.error(f"Failed to run ffmpeg: {error}")
        return False
    finally:
        for stream in (stdout, stderr):
            if hasattr(stream, "close"):
                stream.close()

    if result.returncode != 0:
        if logger is not None:
            logger.error(
                "ffmpeg could not finalize the Agora recording "
                f"(exit code {result.returncode})"
            )
        return False

    if output_path is not None:
        produced = [output_path] if os.path.isfile(output_path) else []
    else:
        after = set(glob.glob(os.path.join(folder, f"*{suffix}.{container}")))
        produced = [path for path in after - before if os.path.isfile(path)]

    produced = [path for path in produced if os.path.getsize(path) >= _MIN_PLAYABLE_SIZE]
    if not produced:
        if logger is not None:
            logger.error("ffmpeg produced no playable Agora recording")
        return False

    try:
        os.unlink(source)
    except OSError:
        pass
    if logger is not None:
        logger.info(f"Agora recording saved: {', '.join(sorted(produced))}")
    return True


class AgoraDownloader:
    def __init__(self, bot, stream: AgoraStream, backend=None):
        self.bot = bot
        self.stream = stream
        self.backend = backend
        self._backend_used = False
        self._active_backend = None
        self._stopped = threading.Event()
        self._lock = threading.Lock()
        self._success = []

    def _make_backend(self):
        if self.backend is not None and not self._backend_used:
            self._backend_used = True
            return self.backend
        return AgoraWebRTCBackend(self.bot.logger)

    def stop(self) -> None:
        """Request a stop.  Safe to call repeatedly and from another thread."""
        self._stopped.set()
        with self._lock:
            backend = self._active_backend
        if backend is not None:
            backend.request_stop()

    def _set_active(self, backend) -> None:
        with self._lock:
            self._active_backend = backend

    def _log(self, level: str, message: str) -> None:
        logger = getattr(self.bot, "logger", None)
        if logger is None:
            return
        getattr(logger, level)(message)

    def record(self, filename: str) -> bool:
        if not self._validate():
            return False
        if self._stopped.is_set():
            return False

        self.bot.stopDownload = self.stop
        part = 0
        credentials = self.stream.credentials
        try:
            while True:
                if self._stopped.is_set():
                    break
                part_filename = _part_filename(filename, part + 1)
                success, restart = self._record_part(credentials, part_filename)
                self._success.append(success)
                if restart is None:
                    break
                self._log(
                    "info",
                    "Agora channel credentials changed; starting a new segment",
                )
                credentials = restart
                self.stream.credentials = restart
                part += 1
        finally:
            self.bot.stopDownload = None
        return bool(self._success) and all(self._success)

    def _validate(self) -> bool:
        credentials = self.stream.credentials
        missing = [
            name for name in ("app_id", "channel", "uid")
            if getattr(credentials, name) in (None, "")
        ]
        if missing:
            self._log(
                "error",
                "Agora stream is missing required credentials: " + ", ".join(missing),
            )
            return False
        if parameters.AGORA_BACKEND.lower() != "webrtc":
            self._log(
                "error",
                f"Unsupported Agora backend {parameters.AGORA_BACKEND!r}; "
                "only 'webrtc' is implemented",
            )
            return False
        if self.stream.preferred_stream not in ("high", "low"):
            self._log(
                "warning",
                f"Unknown Agora stream preference {self.stream.preferred_stream!r}; using high",
            )
            self.stream.preferred_stream = "high"
        return True

    def _record_part(self, credentials: AgoraCredentials, filename: str):
        """Record one file.  Returns ``(success, restart_credentials)``."""
        temp = _temp_filename(filename)
        os.makedirs(os.path.dirname(os.path.abspath(temp)), exist_ok=True)

        backend = self._make_backend()
        try:
            backend.start(
                credentials,
                temp,
                preferred_stream=self.stream.preferred_stream,
                max_duration=parameters.AGORA_MAX_DURATION,
            )
        except AgoraBackendUnavailable as error:
            self._log("error", str(error))
            return False, None
        except Exception as error:  # noqa: BLE001 - a broken sidecar should not kill the bot
            self._log("error", f"Failed to start the Agora recorder: {error}")
            return False, None

        self._set_active(backend)
        started = time.monotonic()
        joined = False
        got_media = False
        failed = False
        restart_credentials = None
        stopped_event = False
        force_refresh = False
        next_refresh_attempt = 0.0

        try:
            while not self._stopped.is_set():
                event = backend.next_event(0.5)
                now = time.monotonic()

                if event is not None:
                    name = event.get("event")
                    if name == "joined":
                        joined = True
                        self._log(
                            "info",
                            f"Agora recorder joined channel {self.stream.credentials.channel}",
                        )
                    elif name == "media":
                        got_media = True
                        width = event.get("width")
                        height = event.get("height")
                        self._log(
                            "info",
                            "Agora recording media: "
                            f"{width}x{height} video={event.get('video', '?')} "
                            f"audio={event.get('audio', '?')}",
                        )
                    elif name == "recording":
                        got_media = True
                        self._log("debug", f"Agora recorder file: {event.get('file')}")
                    elif name == "warning":
                        self._log("warning", "Agora recorder: " + str(event.get("message")))
                    elif name == "error":
                        failed = True
                        self._log(
                            "error",
                            "Agora recorder error: "
                            f"{event.get('message')} (code {event.get('code')})",
                        )
                        stopped_event = True
                    elif name == "token_expiring":
                        force_refresh = True
                    elif name == "stopped":
                        stopped_event = True
                    elif name == "process_exit":
                        code = event.get("code")
                        if code not in (0, None) and not backend.reported_file:
                            failed = True
                            self._log(
                                "error",
                                f"Agora recorder exited with code {code}",
                            )
                        elif code not in (0, None):
                            # A native teardown crash must not discard a file
                            # that was already finalized.
                            self._log(
                                "debug",
                                f"Agora recorder process ended with code {code} "
                                "after finalizing the file",
                            )
                        break

                if self._stopped.is_set() or stopped_event or backend.exited:
                    break

                expiry = credentials.expires_at
                refresh_margin = parameters.AGORA_TOKEN_REFRESH_MARGIN
                wall_now = time.time()
                if expiry is not None and (force_refresh or wall_now >= expiry - refresh_margin):
                    if force_refresh or wall_now >= next_refresh_attempt:
                        new_credentials, restart = self._refresh(credentials, backend)
                        force_refresh = False
                        next_refresh_attempt = wall_now + 30
                        if restart:
                            restart_credentials = new_credentials
                            break
                        if new_credentials is not None:
                            credentials = new_credentials
                            self.stream.credentials = credentials
                        elif wall_now >= expiry:
                            self._log("error", "Agora token expired and could not be refreshed")
                            break
                        else:
                            self._log(
                                "warning",
                                "Agora token refresh failed; keeping the current token "
                                "until it expires",
                            )

                timeout = parameters.AGORA_JOIN_TIMEOUT
                if not got_media and now - started > timeout:
                    self._log(
                        "error",
                        f"Agora recorder received no media within {timeout}s",
                    )
                    failed = True
                    break
                if not joined and now - started > timeout:
                    self._log(
                        "error",
                        f"Agora recorder did not join within {timeout}s",
                    )
                    failed = True
                    break
        except Exception as error:  # noqa: BLE001 - keep the bot alive
            failed = True
            self._log("error", f"Agora recorder failed: {error}")
        finally:
            self._set_active(None)
            try:
                code = backend.close(parameters.AGORA_STOP_TIMEOUT)
                if code not in (0, None):
                    level = "debug" if backend.reported_file else "warning"
                    self._log(level, f"Agora recorder stopped with code {code}")
            except Exception as error:  # noqa: BLE001
                self._log("warning", f"Failed to stop the Agora recorder cleanly: {error}")

        source = self._find_source(backend, temp)
        if source is None:
            if not failed:
                self._log("warning", "Agora recording produced no file")
            return False, restart_credentials

        success = finalize_recording(
            source,
            filename,
            self.bot.logger,
            suffix=getattr(self.bot, "filename_extra_suffix", ""),
        )
        if not success and failed:
            self._log("error", "Agora recording failed and could not be finalized")
        return success, restart_credentials

    def _refresh(self, credentials: AgoraCredentials, backend):
        """Return ``(new_credentials, must_restart)``.

        A token can only be renewed in place when it belongs to the same channel
        and uid.  A different uid/channel needs a new recorder process and a new
        output segment.
        """
        refresh = self.stream.refresh
        if refresh is None:
            return None, False
        try:
            new_credentials = refresh()
        except Exception as error:  # noqa: BLE001 - the old token may still be valid
            self._log("warning", f"Agora token refresh failed: {error}")
            return None, False
        if new_credentials is None:
            return None, False
        if (
            new_credentials.channel != credentials.channel
            or str(new_credentials.uid) != str(credentials.uid)
        ):
            return new_credentials, True
        if not backend.renew_token(new_credentials.token or ""):
            self._log("warning", "Agora token refresh succeeded but could not be sent")
            return None, False
        return new_credentials, False

    @staticmethod
    def _find_source(backend, temp: str) -> str | None:
        reported = getattr(backend, "reported_file", None)
        if reported and os.path.isfile(reported) and os.path.getsize(reported) > 0:
            return reported
        if os.path.isfile(temp) and os.path.getsize(temp) > 0:
            return temp
        base = os.path.splitext(temp)[0]
        candidates = [
            path for path in glob.glob(base + "*.mp4")
            if os.path.isfile(path) and os.path.getsize(path) > 0
        ]
        if not candidates:
            return None
        return max(candidates, key=os.path.getmtime)


class AgoraBot(Bot):
    def __init__(self, username):
        super().__init__(username)
        # Bot.run() calls self.getVideo(self, url, file), so this must remain an
        # unbound function taking the bot as its first argument.
        self.getVideo = getVideoAgora


def getVideoAgora(bot, stream: AgoraStream, filename: str) -> bool:
    return AgoraDownloader(bot, stream).record(filename)
