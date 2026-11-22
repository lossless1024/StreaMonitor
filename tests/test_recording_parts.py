"""Tests for resuming shows across downloader restarts.

A live show can be interrupted several times by network or demuxer errors.
These tests cover the part file naming, the merge that turns those parts back
into a single video, and the ffmpeg watchdog that stops a stalled recording.
"""

from __future__ import annotations

import logging
import os
import shutil
import stat
import subprocess
import time
from datetime import datetime
from itertools import count

import pytest

from streamonitor import bot as bot_module
from streamonitor.bot import Bot
from streamonitor.enums import Status
from streamonitor.downloaders import ffmpeg as ffmpeg_module
from streamonitor.downloaders.ffmpeg import getVideoFfmpeg

FFMPEG = os.environ.get("FFMPEG") or shutil.which("ffmpeg")
FFPROBE = os.environ.get("FFPROBE") or shutil.which("ffprobe")


class FakeBot:
    def __init__(self):
        self.username = "tester"
        self.siteslug = "cb"
        self.logger = logging.getLogger("test-recording-parts")
        self.headers = {"User-Agent": "test-agent"}
        self.cookies = {}
        self.stopDownload = None
        self.filename_extra_suffix = ""


def makeBot(tmp_path, monkeypatch):
    bot = object.__new__(Bot)
    bot.username = "tester"
    bot.siteslug = "cb"
    bot.logger = logging.getLogger("test-recording-parts")
    bot.recording_base = None
    bot.recording_parts = []
    bot._recording_disconnect_at = None
    bot.RECONNECT_GRACE_SECONDS = 45
    numbers = count(1)

    def genOutFilename(create_dir=True):
        # Distinct names, unlike the second resolution timestamps of a real run.
        return str(tmp_path / f"tester-20260101-00{next(numbers):04d}.mp4")

    bot.genOutFilename = genOutFilename
    return bot


def testOutputFolderUsesDateFolderByDefault(tmp_path, monkeypatch):
    bot = makeBot(tmp_path, monkeypatch)
    monkeypatch.setattr(bot_module, "DOWNLOADS_DIR", str(tmp_path))
    monkeypatch.setattr(bot_module, "DOWNLOADS_BY_DATE", True)
    monkeypatch.setattr(bot_module, "DOWNLOAD_DATE_FORMAT", "%Y-%m-%d")

    folder = bot.outputFolder

    assert os.path.basename(os.path.dirname(folder)) == datetime.now().strftime("%Y-%m-%d")
    assert folder == str(tmp_path / datetime.now().strftime("%Y-%m-%d") / "tester [cb]")


def testOutputFolderUsesSingleFolderWithDateDisabled(tmp_path, monkeypatch):
    bot = makeBot(tmp_path, monkeypatch)
    monkeypatch.setattr(bot_module, "DOWNLOADS_DIR", str(tmp_path))
    monkeypatch.setattr(bot_module, "DOWNLOADS_BY_DATE", False)

    folder = bot.outputFolder

    assert folder == str(tmp_path / "tester [cb]")


def testDateFolderIsReusedWithoutDeletingExistingFiles(tmp_path, monkeypatch):
    bot = object.__new__(Bot)
    bot.username = "tester"
    bot.siteslug = "cb"
    bot._download_date_folder = datetime.now().strftime("%Y-%m-%d")
    monkeypatch.setattr(bot_module, "DOWNLOADS_DIR", str(tmp_path))
    monkeypatch.setattr(bot_module, "DOWNLOADS_BY_DATE", True)
    monkeypatch.setattr(bot_module, "DOWNLOAD_DATE_FORMAT", "%Y-%m-%d")

    folder = bot.outputFolder
    os.makedirs(folder, exist_ok=True)
    existing = os.path.join(folder, "existing.mkv")
    open(existing, "wb").write(b"keep")

    assert os.path.exists(existing)
    assert bot.outputFolder == folder
    with open(existing, "rb") as existing_file:
        assert existing_file.read() == b"keep"


def testGenOutFilenameDoesNotOverwriteExistingFile(tmp_path, monkeypatch):
    bot = object.__new__(Bot)
    bot.username = "tester"
    bot.siteslug = "cb"
    bot._download_date_folder = "2026-11-21"
    monkeypatch.setattr(bot_module, "DOWNLOADS_DIR", str(tmp_path))
    monkeypatch.setattr(bot_module, "DOWNLOADS_BY_DATE", False)

    first = bot.genOutFilename()
    open(first, "wb").write(b"first")
    second = bot.genOutFilename()

    assert first != second
    assert os.path.exists(first)
    with open(first, "rb") as first_file:
        assert first_file.read() == b"first"


def writeVideo(path, seconds=1):
    subprocess.run(
        [FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", f"testsrc=size=160x120:rate=15:duration={seconds}",
         "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
         "-c:v", "mpeg4", "-q:v", "5", "-c:a", "aac", "-shortest", path],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def probeDuration(path):
    result = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", path],
        check=True, capture_output=True, text=True)
    return float(result.stdout.strip())


def testNextRecordingFilenameReusesShowBase(tmp_path, monkeypatch):
    bot = makeBot(tmp_path, monkeypatch)
    monkeypatch.setattr(bot_module, "SEGMENT_TIME", None)

    base = bot.nextRecordingFilename()
    assert base.endswith(".mp4")
    assert bot.hasRecordingInProgress()

    second = bot.nextRecordingFilename()
    third = bot.nextRecordingFilename()
    stem, ext = os.path.splitext(base)
    assert second == f"{stem}.part1{ext}"
    assert third == f"{stem}.part2{ext}"
    assert bot.recording_parts == [base, second, third]


def testNextRecordingFilenameStartsNewShowAfterFinalize(tmp_path, monkeypatch):
    bot = makeBot(tmp_path, monkeypatch)
    monkeypatch.setattr(bot_module, "SEGMENT_TIME", None)

    first = bot.nextRecordingFilename()
    bot.finalizeRecording()
    assert not bot.hasRecordingInProgress()

    second = bot.nextRecordingFilename()
    assert second != first
    assert second.endswith(".mp4")


def testSegmentModeNeverReusesBase(tmp_path, monkeypatch):
    bot = makeBot(tmp_path, monkeypatch)
    monkeypatch.setattr(bot_module, "SEGMENT_TIME", 300)

    first = bot.nextRecordingFilename()
    second = bot.nextRecordingFilename()
    assert first != second
    assert ".part" not in second


def testReconnectKeepsRecordingOpenDuringTemporaryOffline(tmp_path, monkeypatch):
    bot = makeBot(tmp_path, monkeypatch)
    base = bot.nextRecordingFilename()

    now = 1000.0
    assert bot.reconcileRecordingConnection(Status.OFFLINE, now=now) is False
    assert bot.reconcileRecordingConnection(
        Status.OFFLINE,
        now=now + bot.RECONNECT_GRACE_SECONDS - 1,
    ) is False
    assert bot.reconcileRecordingConnection(
        Status.PUBLIC,
        now=now + bot.RECONNECT_GRACE_SECONDS - 1,
    ) is False
    assert bot.hasRecordingInProgress()

    assert bot.reconcileRecordingConnection(
        Status.OFFLINE,
        now=2000.0,
    ) is False
    assert bot.reconcileRecordingConnection(
        Status.OFFLINE,
        now=2000.0 + bot.RECONNECT_GRACE_SECONDS - 1,
    ) is False
    assert bot.reconcileRecordingConnection(
        Status.OFFLINE,
        now=2000.0 + bot.RECONNECT_GRACE_SECONDS,
    ) is True


def testFinalizeMergesPartsIntoOneFile(tmp_path, monkeypatch):
    if not FFMPEG or not FFPROBE:
        pytest.skip("ffmpeg and ffprobe are required")

    bot = makeBot(tmp_path, monkeypatch)
    monkeypatch.setattr(bot_module, "SEGMENT_TIME", None)
    monkeypatch.setattr(bot_module, "FFMPEG_PATH", FFMPEG)

    base = bot.nextRecordingFilename()
    second = bot.nextRecordingFilename()
    writeVideo(base, seconds=1)
    writeVideo(second, seconds=1)

    bot.finalizeRecording()

    assert os.path.exists(base)
    assert not os.path.exists(second)
    assert not os.path.exists(os.path.splitext(base)[0] + ".concat.txt")
    assert probeDuration(base) == pytest.approx(2.0, abs=0.5)
    assert bot.recording_parts == []
    assert not bot.hasRecordingInProgress()


def testFinalizeMergesFragmentedParts(tmp_path, monkeypatch):
    if not FFMPEG or not FFPROBE:
        pytest.skip("ffmpeg and ffprobe are required")

    bot = makeBot(tmp_path, monkeypatch)
    monkeypatch.setattr(bot_module, "SEGMENT_TIME", None)
    monkeypatch.setattr(bot_module, "FFMPEG_PATH", FFMPEG)

    base = bot.nextRecordingFilename()
    second = bot.nextRecordingFilename()
    for path in (base, second):
        subprocess.run(
            [FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
             "-f", "lavfi", "-i", "testsrc=size=160x120:rate=15:duration=1",
             "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
             "-c:v", "mpeg4", "-q:v", "5", "-c:a", "aac", "-shortest",
             "-movflags", "+frag_keyframe+empty_moov", "-f", "mp4", path],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    bot.finalizeRecording()

    assert os.path.exists(base)
    assert not os.path.exists(second)
    assert probeDuration(base) == pytest.approx(2.0, abs=0.5)


def testFinalizeKeepsDamagedPart(tmp_path, monkeypatch):
    if not FFMPEG:
        pytest.skip("ffmpeg is required")

    bot = makeBot(tmp_path, monkeypatch)
    monkeypatch.setattr(bot_module, "SEGMENT_TIME", None)
    monkeypatch.setattr(bot_module, "FFMPEG_PATH", FFMPEG)

    base = bot.nextRecordingFilename()
    second = bot.nextRecordingFilename()
    writeVideo(base, seconds=1)
    with open(second, "wb") as broken:
        broken.write(b"not a video" * 100)

    bot.finalizeRecording()

    assert os.path.getsize(base) > 0
    assert os.path.getsize(second) > 0


def testFinalizeDropsEmptyParts(tmp_path, monkeypatch):
    if not FFMPEG:
        pytest.skip("ffmpeg is required")

    bot = makeBot(tmp_path, monkeypatch)
    monkeypatch.setattr(bot_module, "SEGMENT_TIME", None)
    monkeypatch.setattr(bot_module, "FFMPEG_PATH", FFMPEG)

    base = bot.nextRecordingFilename()
    second = bot.nextRecordingFilename()
    third = bot.nextRecordingFilename()
    writeVideo(base, seconds=1)
    open(second, "wb").close()  # ffmpeg never wrote anything
    writeVideo(third, seconds=1)

    bot.finalizeRecording()

    assert os.path.exists(base)
    assert not os.path.exists(second)
    assert not os.path.exists(third)
    assert probeDuration(base) == pytest.approx(2.0, abs=0.5)


def testFinalizeRenamesSingleRemainingPart(tmp_path, monkeypatch):
    if not FFMPEG:
        pytest.skip("ffmpeg is required")

    bot = makeBot(tmp_path, monkeypatch)
    monkeypatch.setattr(bot_module, "SEGMENT_TIME", None)
    monkeypatch.setattr(bot_module, "FFMPEG_PATH", FFMPEG)

    base = bot.nextRecordingFilename()
    second = bot.nextRecordingFilename()
    open(base, "wb").close()  # the first attempt failed before writing
    writeVideo(second, seconds=1)

    bot.finalizeRecording()

    assert os.path.exists(base)
    assert os.path.getsize(base) > 0
    assert not os.path.exists(second)


def makeFakeFfmpeg(tmp_path, body):
    path = tmp_path / "fake-ffmpeg"
    path.write_text("#!/bin/sh\n" + body + "\n")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return str(path)


def testWatchdogStopsStalledRecording(tmp_path, monkeypatch):
    output = tmp_path / "tester-20260101-000000.mp4"
    fake = makeFakeFfmpeg(tmp_path, f"echo x > '{output}'; sleep 30")
    monkeypatch.setattr(ffmpeg_module, "FFMPEG_PATH", fake)
    monkeypatch.setattr(ffmpeg_module, "FFMPEG_READRATE", 0)
    monkeypatch.setattr(ffmpeg_module, "FFMPEG_STALL_TIMEOUT", 2)

    fbot = FakeBot()
    started = time.monotonic()
    result = getVideoFfmpeg(fbot, "https://example.com/live.m3u8", str(output))
    elapsed = time.monotonic() - started

    assert result is False
    assert elapsed < 25


def testWatchdogLeavesGrowingRecordingAlone(tmp_path, monkeypatch):
    output = tmp_path / "tester-20260101-000000.mp4"
    fake = makeFakeFfmpeg(
        tmp_path,
        f"for i in 1 2 3 4 5 6 7 8; do echo x >> '{output}'; sleep 0.3; done")
    monkeypatch.setattr(ffmpeg_module, "FFMPEG_PATH", fake)
    monkeypatch.setattr(ffmpeg_module, "FFMPEG_READRATE", 0)
    monkeypatch.setattr(ffmpeg_module, "FFMPEG_STALL_TIMEOUT", 2)

    fbot = FakeBot()
    result = getVideoFfmpeg(fbot, "https://example.com/live.m3u8", str(output))

    assert result is True
    assert output.stat().st_size > 0


def testReadrateIsOmittedWhenDisabled(tmp_path, monkeypatch):
    args_file = tmp_path / "args"
    fake = makeFakeFfmpeg(tmp_path, f"printf '%s\\n' \"$@\" > '{args_file}'")
    monkeypatch.setattr(ffmpeg_module, "FFMPEG_PATH", fake)
    monkeypatch.setattr(ffmpeg_module, "FFMPEG_STALL_TIMEOUT", 0)
    monkeypatch.setattr(ffmpeg_module, "FFMPEG_READRATE", 0)

    fbot = FakeBot()
    getVideoFfmpeg(fbot, "https://example.com/live.m3u8",
                   str(tmp_path / "tester-20260101-000000.mp4"))

    assert "-readrate" not in args_file.read_text().splitlines()


def testMp4OutputIsFragmentedSoPartsSurviveKills(tmp_path, monkeypatch):
    args_file = tmp_path / "args"
    fake = makeFakeFfmpeg(tmp_path, f"printf '%s\\n' \"$@\" > '{args_file}'")
    monkeypatch.setattr(ffmpeg_module, "FFMPEG_PATH", fake)
    monkeypatch.setattr(ffmpeg_module, "FFMPEG_STALL_TIMEOUT", 0)
    monkeypatch.setattr(ffmpeg_module, "FFMPEG_READRATE", 0)
    monkeypatch.setattr(ffmpeg_module, "CONTAINER", "mp4")

    fbot = FakeBot()
    getVideoFfmpeg(fbot, "https://example.com/live.m3u8",
                   str(tmp_path / "tester-20260101-000000.mp4"))

    args = args_file.read_text().splitlines()
    flags = args[args.index("-movflags") + 1]
    assert flags == "+frag_keyframe"
    # +empty_moov disables ffmpeg's automatic bitstream filtering, which
    # breaks ADTS AAC streams (Cam4 and other MPEG-TS HLS sources).
    assert "empty_moov" not in flags


def testOtherContainersAreNotFragmented(tmp_path, monkeypatch):
    args_file = tmp_path / "args"
    fake = makeFakeFfmpeg(tmp_path, f"printf '%s\\n' \"$@\" > '{args_file}'")
    monkeypatch.setattr(ffmpeg_module, "FFMPEG_PATH", fake)
    monkeypatch.setattr(ffmpeg_module, "FFMPEG_STALL_TIMEOUT", 0)
    monkeypatch.setattr(ffmpeg_module, "FFMPEG_READRATE", 0)
    monkeypatch.setattr(ffmpeg_module, "CONTAINER", "mkv")

    fbot = FakeBot()
    getVideoFfmpeg(fbot, "https://example.com/live.m3u8",
                   str(tmp_path / "tester-20260101-000000.mkv"))

    assert "-movflags" not in args_file.read_text().splitlines()


def testReadrateIsPassedWhenConfigured(tmp_path, monkeypatch):
    args_file = tmp_path / "args"
    fake = makeFakeFfmpeg(tmp_path, f"printf '%s\\n' \"$@\" > '{args_file}'")
    monkeypatch.setattr(ffmpeg_module, "FFMPEG_PATH", fake)
    monkeypatch.setattr(ffmpeg_module, "FFMPEG_STALL_TIMEOUT", 0)
    monkeypatch.setattr(ffmpeg_module, "FFMPEG_READRATE", 1.3)

    fbot = FakeBot()
    getVideoFfmpeg(fbot, "https://example.com/live.m3u8",
                   str(tmp_path / "tester-20260101-000000.mp4"))

    args = args_file.read_text().splitlines()
    assert args[args.index("-readrate") + 1] == "1.3"


def makeRecoveryBot(tmp_path, monkeypatch, container="mkv"):
    """Bot whose download folder holds files left by a killed process."""
    bot = object.__new__(Bot)
    bot.username = "tester"
    bot.siteslug = "cb"
    bot.logger = logging.getLogger("test-recording-recovery")
    bot.recording_base = None
    bot.recording_parts = []
    bot.video_files = []
    bot.video_files_total_size = 0
    folder = tmp_path / "tester [cb]"
    folder.mkdir(exist_ok=True)
    monkeypatch.setattr(bot_module, "DOWNLOADS_DIR", str(tmp_path))
    monkeypatch.setattr(bot_module, "CONTAINER", container)
    monkeypatch.setattr(bot_module, "FFMPEG_PATH", FFMPEG)
    monkeypatch.setattr(bot_module, "SEGMENT_TIME", None)
    return bot, folder


def writeTs(path, seconds=1):
    subprocess.run(
        [FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", f"testsrc=size=160x120:rate=15:duration={seconds}",
         "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
         "-c:v", "mpeg2video", "-c:a", "mp2", "-shortest",
         "-f", "mpegts", str(path)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def testRecoveryMergesOrphanedPartsOnStartup(tmp_path, monkeypatch):
    if not FFMPEG or not FFPROBE:
        pytest.skip("ffmpeg and ffprobe are required")

    bot, folder = makeRecoveryBot(tmp_path, monkeypatch)
    base = folder / "tester-20260101-000000.mkv"
    first = folder / "tester-20260101-000000.part1.mkv"
    second = folder / "tester-20260101-000000.part2.mkv"
    writeVideo(str(base), 1)
    writeVideo(str(first), 1)
    writeVideo(str(second), 1)

    bot.recoverOrphanedRecordings()

    assert os.path.exists(base)
    assert not first.exists()
    assert not second.exists()
    assert probeDuration(str(base)) == pytest.approx(3.0, abs=0.7)


def testRecoveryKeepsSingleOrphanPartAsBase(tmp_path, monkeypatch):
    if not FFMPEG or not FFPROBE:
        pytest.skip("ffmpeg and ffprobe are required")

    bot, folder = makeRecoveryBot(tmp_path, monkeypatch)
    base = folder / "tester-20260101-000000.mkv"
    part = folder / "tester-20260101-000000.part1.mkv"
    writeVideo(str(part), 1)

    bot.recoverOrphanedRecordings()

    assert base.exists()
    assert not part.exists()
    assert probeDuration(str(base)) == pytest.approx(1.0, abs=0.5)


def canReadMpegts(tmp_path):
    """Some static ffmpeg builds crash on MPEG-TS input; skip the real remux."""
    if not FFMPEG:
        return False
    sample = tmp_path / "probe.tmp.ts"
    writeTs(sample, seconds=1)
    result = subprocess.run(
        [FFMPEG, "-v", "error", "-i", str(sample), "-f", "null", "-"],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    sample.unlink()
    return result.returncode == 0


def testRecoveryRemuxesInterruptedTempDownload(tmp_path, monkeypatch):
    if not FFPROBE or not canReadMpegts(tmp_path):
        pytest.skip("ffmpeg with a working MPEG-TS demuxer is required")

    bot, folder = makeRecoveryBot(tmp_path, monkeypatch)
    temp = folder / "tester-20260101-000000.tmp.ts"
    writeTs(temp, seconds=1)

    bot.recoverOrphanedRecordings()

    target = folder / "tester-20260101-000000.mkv"
    assert target.exists()
    assert not temp.exists()
    assert probeDuration(str(target)) == pytest.approx(1.0, abs=0.5)


def testRecoveryRemuxesTempIntoRecordingName(tmp_path, monkeypatch):
    """The temp file becomes a normal recording, then joins the show."""
    bot, folder = makeRecoveryBot(tmp_path, monkeypatch)
    fake = makeFakeFfmpeg(
        tmp_path,
        'prev=""; in=""; out=""\n'
        'for a in "$@"; do\n'
        '  [ "$prev" = "-i" ] && in="$a"\n'
        '  out="$a"; prev="$a"\n'
        'done\n'
        'cp "$in" "$out"')
    monkeypatch.setattr(bot_module, "FFMPEG_PATH", fake)

    temp = folder / "tester-20260101-000000.tmp.ts"
    temp.write_bytes(b"raw-ts-bytes")

    bot.recoverOrphanedRecordings()

    target = folder / "tester-20260101-000000.mkv"
    assert target.read_bytes() == b"raw-ts-bytes"
    assert not temp.exists()


def testRecoveryMergesInterruptedTempPartIntoShow(tmp_path, monkeypatch):
    if not FFPROBE or not canReadMpegts(tmp_path):
        pytest.skip("ffmpeg with a working MPEG-TS demuxer is required")

    bot, folder = makeRecoveryBot(tmp_path, monkeypatch)
    base = folder / "tester-20260101-000000.mkv"
    temp = folder / "tester-20260101-000000.part1.tmp.ts"
    writeVideo(str(base), 1)
    writeTs(temp, seconds=1)

    bot.recoverOrphanedRecordings()

    assert not temp.exists()
    assert probeDuration(str(base)) == pytest.approx(2.0, abs=0.7)


def testRecoveryDropsEmptyTempFileAndMergeLeftovers(tmp_path, monkeypatch):
    bot, folder = makeRecoveryBot(tmp_path, monkeypatch)
    temp = folder / "tester-20260101-000000.tmp.ts"
    temp.touch()
    concat = folder / "tester-20260101-000000.concat.txt"
    concat.write_text("file 'x'\n")
    merged = folder / "tester-20260101-000000.merged.mkv"
    merged.write_bytes(b"partial")

    bot.recoverOrphanedRecordings()

    assert not temp.exists()
    assert not concat.exists()
    assert not merged.exists()


def testRecoveryLeavesFinishedRecordingsAlone(tmp_path, monkeypatch):
    bot, folder = makeRecoveryBot(tmp_path, monkeypatch)
    finished = folder / "tester-20260101-000000.mkv"
    finished.write_bytes(b"already fine")
    mtime = finished.stat().st_mtime

    bot.recoverOrphanedRecordings()

    assert finished.read_bytes() == b"already fine"
    assert finished.stat().st_mtime == mtime


def testRecoveryRunsOnlyOnce(tmp_path, monkeypatch):
    bot, folder = makeRecoveryBot(tmp_path, monkeypatch)
    scans = []
    monkeypatch.setattr(
        bot, "_orphanedPartGroups",
        lambda folder: scans.append(folder) or {})

    bot.recoverOrphanedRecordings()
    bot.recoverOrphanedRecordings()

    assert len(scans) == 1
