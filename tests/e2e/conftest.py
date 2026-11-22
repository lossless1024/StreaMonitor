"""Shared setup for the opt-in live recording tests."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
E2E_ROOT = Path(__file__).resolve().parent
for path in (str(REPO_ROOT), str(E2E_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)


def _find_binary(env_name: str, name: str) -> str | None:
    configured = os.environ.get(env_name)
    if configured:
        candidate = shutil.which(configured) or configured
        if Path(candidate).is_file():
            return str(Path(candidate).resolve())
    found = shutil.which(name)
    return str(Path(found).resolve()) if found else None


def _find_ffmpeg() -> str | None:
    found = _find_binary("STRMNTR_FFMPEG_PATH", "ffmpeg")
    if found:
        return found
    # Some development containers unpack ffmpeg under ~/.cache instead of
    # putting it on PATH.  Use it when present so no extra setup is needed.
    for pattern in ("ffmpeg*/ffmpeg-*/bin/ffmpeg", "ffmpeg*/bin/ffmpeg"):
        cached = sorted(Path.home().glob(f".cache/{pattern}"))
        for candidate in reversed(cached):
            if candidate.is_file():
                return str(candidate)
    return None


def _find_ffprobe() -> str | None:
    found = _find_binary("STRMNTR_FFPROBE_PATH", "ffprobe")
    if found:
        return found
    ffmpeg = _find_ffmpeg()
    if ffmpeg:
        sibling = Path(ffmpeg).with_name("ffprobe")
        if sibling.is_file():
            return str(sibling)
    return None


FFMPEG = _find_ffmpeg()
FFPROBE = _find_ffprobe()

# parameters.py reads this at import time.  Set it before the test module (or
# any application module) is imported.
if FFMPEG and not os.environ.get("STRMNTR_FFMPEG_PATH"):
    os.environ["STRMNTR_FFMPEG_PATH"] = FFMPEG

# The Agora recorder needs a JVM, the native SDK and an RTC join; give it more
# startup room than the HLS sites in the opt-in tests.
os.environ.setdefault("STRMNTR_AGORA_JOIN_TIMEOUT", "90")


def e2e_enabled() -> bool:
    return os.environ.get("STRMNTR_E2E") == "1"


def pytest_collection_modifyitems(config, items):
    if e2e_enabled():
        return
    skip = pytest.mark.skip(
        reason="live end-to-end tests are opt-in; set STRMNTR_E2E=1 to run them"
    )
    for item in items:
        if "e2e" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def download_root(tmp_path_factory):
    import parameters as parameters_module
    import streamonitor.bot as bot_module

    root = tmp_path_factory.mktemp("streamonitor-e2e-downloads")
    bot_module.DOWNLOADS_DIR = str(root)
    parameters_module.DOWNLOADS_DIR = str(root)
    yield root


@pytest.fixture(scope="session")
def ffmpeg_bin():
    if not FFMPEG:
        pytest.skip("ffmpeg is not installed or STRMNTR_FFMPEG_PATH is invalid")
    return FFMPEG


@pytest.fixture(scope="session")
def ffprobe_bin():
    if not FFPROBE:
        pytest.skip("ffprobe is not installed or STRMNTR_FFPROBE_PATH is invalid")
    return FFPROBE


@pytest.fixture
def record_seconds() -> int:
    value = int(os.environ.get("STRMNTR_E2E_RECORD_SECONDS", "20"))
    return max(5, value)
