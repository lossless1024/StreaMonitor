"""Subprocess backend for the Python Agora WebRTC worker.

The worker joins Agora through its web gateway with aiortc and writes MP4 with
PyAV; there is no JVM, Maven build, or Agora native SDK.  Keeping it in a child
process isolates a crashed codec or network stack from the monitor.

Only this module knows about the subprocess and its JSON-line wire format.
"""

from __future__ import annotations

import importlib.util
import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
from collections import deque

import parameters

_REQUIRED_MODULES = ("aiortc", "av", "numpy", "websockets")


class AgoraBackendUnavailable(RuntimeError):
    """The Python Agora worker cannot be started on this host."""


class AgoraWebRTCBackend:
    """Subprocess backend for the Python Agora web-gateway recorder."""

    def __init__(self, logger=None):
        self.logger = logger
        self._events: queue.Queue = queue.Queue()
        self._stderr = deque(maxlen=40)
        self._process: subprocess.Popen | None = None
        self._stdout_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._token: str | None = None
        self._config_path: str | None = None
        self.reported_file: str | None = None
        self.media: dict | None = None
        self.exit_code: int | None = None

    # -- discovery ---------------------------------------------------------

    @classmethod
    def python_path(cls) -> str:
        return shutil.which(parameters.AGORA_PYTHON) or parameters.AGORA_PYTHON

    @classmethod
    def available(cls) -> bool:
        if any(importlib.util.find_spec(name) is None for name in _REQUIRED_MODULES):
            return False
        return (
            os.path.isfile(cls.worker_path())
            and (shutil.which(cls.python_path()) is not None
                 or os.path.isfile(cls.python_path()))
        )

    @staticmethod
    def worker_path() -> str:
        return os.path.abspath(
            os.path.join(os.path.dirname(__file__), "agora_worker.py")
        )

    @staticmethod
    def project_root() -> str:
        return os.path.abspath(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        )

    # -- lifecycle ---------------------------------------------------------

    def start(self, credentials, output: str, preferred_stream: str = "high",
              max_duration: int = 0) -> None:
        if not self.available():
            raise AgoraBackendUnavailable(
                "Agora WebRTC recorder is not available: install aiortc, av, "
                f"numpy and websockets (python={self.python_path()})"
            )

        self._token = credentials.token
        self.reported_file = None
        self.media = None
        self.exit_code = None

        config = {
            "appId": credentials.app_id,
            "channel": credentials.channel,
            "token": credentials.token or "",
            "uid": str(credentials.uid),
            "output": output,
            "streamType": preferred_stream,
            "maxDurationSec": max(0, int(max_duration or 0)),
            "userAgent": parameters.HTTP_USER_AGENT,
        }

        fd, self._config_path = tempfile.mkstemp(prefix=".agora-", suffix=".json")
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w") as config_file:
                json.dump(config, config_file)
        except BaseException:
            self._delete_config()
            raise

        root = self.project_root()
        env = os.environ.copy()
        env["PYTHONPATH"] = root + os.pathsep + env.get("PYTHONPATH", "")
        cmd = [
            self.python_path(),
            "-m", "streamonitor.downloaders.agora_worker",
            "--config", self._config_path,
        ]
        try:
            self._process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                cwd=root,
                env=env,
            )
        except OSError as error:
            self._delete_config()
            raise AgoraBackendUnavailable(
                f"failed to start Agora WebRTC worker: {error}"
            ) from error

        self._stdout_thread = threading.Thread(
            target=self._read_stdout, name="agora-worker-events", daemon=True)
        self._stdout_thread.start()
        self._stderr_thread = threading.Thread(
            target=self._read_stderr, name="agora-worker-stderr", daemon=True)
        self._stderr_thread.start()

    def _delete_config(self) -> None:
        path, self._config_path = self._config_path, None
        if path:
            try:
                os.unlink(path)
            except OSError:
                pass

    def _read_stdout(self) -> None:
        process = self._process
        if process is None or process.stdout is None:
            return
        for raw in process.stdout:
            line = raw.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except ValueError:
                self._debug(f"recorder: {self._redact(line)}")
                continue
            if not isinstance(event, dict) or "event" not in event:
                self._debug(f"recorder: {self._redact(line)}")
                continue

            if event.get("file"):
                self.reported_file = event["file"]
            if event["event"] == "media":
                self.media = event
            if event["event"] in ("joined", "recording", "stopped", "error"):
                # The worker has read the config by now.
                self._delete_config()
            self._events.put(event)
        code = process.wait()
        self.exit_code = code
        self._delete_config()
        self._events.put({"event": "process_exit", "code": code})

    def _read_stderr(self) -> None:
        process = self._process
        if process is None or process.stderr is None:
            return
        for raw in process.stderr:
            line = self._redact(raw.strip())
            if line:
                self._stderr.append(line)
                self._debug(f"recorder: {line}")

    def _redact(self, text: str) -> str:
        token = self._token
        if token and token in text:
            return text.replace(token, "<redacted>")
        return text

    def _debug(self, message: str) -> None:
        if self.logger is not None:
            self.logger.debug(message)

    # -- events and commands ----------------------------------------------

    def next_event(self, timeout: float = 0.5) -> dict | None:
        try:
            return self._events.get(timeout=timeout)
        except queue.Empty:
            return None

    @property
    def exited(self) -> bool:
        return self._process is not None and self._process.poll() is not None

    def request_stop(self) -> None:
        """Ask the worker to stop without blocking the caller."""
        with self._lock:
            process = self._process
            if process is None or process.poll() is not None or process.stdin is None:
                return
            try:
                process.stdin.write("stop\n")
                process.stdin.flush()
            except (BrokenPipeError, OSError, ValueError):
                pass

    def renew_token(self, token: str) -> bool:
        with self._lock:
            process = self._process
            if process is None or process.poll() is not None or process.stdin is None:
                return False
            try:
                self._token = token
                process.stdin.write(json.dumps({"command": "renew", "token": token}) + "\n")
                process.stdin.flush()
                return True
            except (BrokenPipeError, OSError, ValueError):
                return False

    def wait(self, timeout: float) -> int | None:
        process = self._process
        if process is None:
            return self.exit_code
        try:
            return process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            return None

    def terminate(self) -> None:
        process = self._process
        if process is not None and process.poll() is None:
            process.terminate()

    def kill(self) -> None:
        process = self._process
        if process is not None and process.poll() is None:
            process.kill()

    def close(self, timeout: float = 15) -> int | None:
        """Stop the worker gracefully, escalating to SIGTERM and SIGKILL."""
        self.request_stop()
        code = self.wait(timeout)
        if code is None:
            self.terminate()
            code = self.wait(5)
        if code is None:
            self.kill()
            code = self.wait(5)
        if self._process is not None and self._process.stdin is not None:
            try:
                self._process.stdin.close()
            except OSError:
                pass
        self._delete_config()
        return code

    def stderr_tail(self) -> str:
        return "\n".join(self._stderr)


# Backwards-compatible name for callers that imported the old backend.
AgoraNativeBackend = AgoraWebRTCBackend
