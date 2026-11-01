import errno
import os
import subprocess
import sys
import threading
import time

import requests.cookies
from threading import Thread
from parameters import DEBUG, SEGMENT_TIME, CONTAINER, FFMPEG_PATH, FFMPEG_READRATE, FFMPEG_STALL_TIMEOUT


def _buildInputArgs(url):
    if isinstance(url, os.PathLike):
        local_playlist = os.fspath(url)
        return (
            ['-protocol_whitelist', 'file,http,https,tcp,tls,crypto,data', '-i', local_playlist],
            local_playlist,
        )
    return ['-i', url], None


def _stopProcess(process, stop_lock, timeout=10):
    """Ask ffmpeg to quit, then kill it if it does not exit in time."""
    with stop_lock:
        if process.poll() is not None:
            return
        try:
            process.communicate(b'q', timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                process.kill()
            except OSError:
                pass
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        except (ValueError, OSError):
            pass


def getVideoFfmpeg(self, url, filename):
    is_local_playlist = isinstance(url, os.PathLike)
    cmd = [FFMPEG_PATH]

    # HTTP protocol options are rejected by ffmpeg when the input is a local
    # playlist. Chaturbate's chunklists only need the session token embedded in
    # their URLs, so they work without the cookie and user-agent options.
    if not is_local_playlist:
        cmd.extend([
            '-user_agent', self.headers['User-Agent']
        ])

        if type(self.cookies) is requests.cookies.RequestsCookieJar:
            cookies_text = ''
            for cookie in self.cookies:
                cookies_text += cookie.name + "=" + cookie.value + "; path=" + cookie.path + '; domain=' + cookie.domain + '\n'
            if len(cookies_text) > 10:
                cookies_text = cookies_text[:-1]
            cmd.extend([
                '-cookies', cookies_text
            ])

    if FFMPEG_READRATE:
        cmd.extend(['-readrate', f'{FFMPEG_READRATE!s}'])

    # These are HLS demuxer options. FFmpeg refuses to start when they are
    # passed for a non-HLS input (e.g. AmateurTV's progressive fMP4 stream).
    if is_local_playlist or '.m3u8' in str(url).lower():
        cmd.extend([
            '-max_reload', '20',
            '-seg_max_retry', '20',
            '-m3u8_hold_counters', '20',
        ])

    # CMAF master playlists are written to a local temporary file so ffmpeg can
    # align the separate audio and video renditions by program date time.
    input_args, local_playlist = _buildInputArgs(url)
    cmd.extend(input_args)
    cmd.extend(['-c:a', 'copy', '-c:v', 'copy'])

    suffix = ''
    if hasattr(self, 'filename_extra_suffix'):
        suffix = self.filename_extra_suffix

    output_path = None
    if SEGMENT_TIME is not None:
        username = filename.rsplit('-', maxsplit=2)[0]
        cmd.extend([
            '-f', 'segment',
            '-reset_timestamps', '1',
            '-segment_time', str(SEGMENT_TIME),
            '-strftime', '1',
            f'{username}-%Y%m%d-%H%M%S{suffix}.{CONTAINER}'
        ])
    else:
        output_path = os.path.splitext(filename)[0] + suffix + '.' + CONTAINER
        # A recording can be interrupted and resumed, so every output file has
        # to stay readable on its own. Fragmented mp4 keeps the index in front
        # of every fragment, unlike a regular mp4 that is unplayable when
        # ffmpeg is killed before it writes the index.
        if CONTAINER == 'mp4':
            cmd.extend(['-movflags', '+frag_keyframe+empty_moov'])
        cmd.extend([output_path])

    class _Stopper:
        def __init__(self):
            self.stop = False

        def pls_stop(self):
            self.stop = True

    stopping = _Stopper()
    stop_lock = threading.Lock()
    error = False
    stalled = False

    def outputSize():
        """Current size of the recording, used to detect a stalled ffmpeg."""
        if output_path is None:
            return 0
        try:
            return os.path.getsize(output_path)
        except OSError:
            return 0

    def watch(process):
        nonlocal stalled
        last_size = outputSize()
        last_change = time.monotonic()
        # A stream that never starts is only stopped after a longer grace
        # period, so slow connections are not killed during startup.
        startup_timeout = max(FFMPEG_STALL_TIMEOUT * 3, 120)
        while process.poll() is None:
            time.sleep(2)
            if process.poll() is not None:
                return
            size = outputSize()
            if size != last_size:
                last_size = size
                last_change = time.monotonic()
                continue
            timeout = FFMPEG_STALL_TIMEOUT if last_size > 0 else startup_timeout
            if time.monotonic() - last_change >= timeout:
                stalled = True
                self.logger.error(
                    f'No output for {timeout}s, stopping the stalled recording')
                _stopProcess(process, stop_lock)
                return

    def execute():
        nonlocal error
        try:
            stderr = open(filename + '.stderr.log', 'w+') if DEBUG else subprocess.DEVNULL
            startupinfo = None
            if sys.platform == "win32":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            process = subprocess.Popen(
                args=cmd, stdin=subprocess.PIPE, stderr=stderr, stdout=subprocess.DEVNULL, startupinfo=startupinfo)
        except OSError as e:
            if e.errno == errno.ENOENT:
                self.logger.error('FFMpeg executable not found!')
                error = True
                return
            else:
                self.logger.error("Got OSError, errno: " + str(e.errno))
                error = True
                return

        # Segment mode writes files with names ffmpeg chooses, so progress is
        # not tracked there.
        if FFMPEG_STALL_TIMEOUT and output_path is not None:
            Thread(target=watch, args=(process,), daemon=True).start()

        while process.poll() is None:
            if stopping.stop:
                _stopProcess(process, stop_lock)
                break
            try:
                process.wait(1)
            except subprocess.TimeoutExpired:
                pass

        if stalled:
            error = True
            return

        if process.returncode and process.returncode != 0 and process.returncode != 255:
            self.logger.error('The process exited with an error. Return code: ' + str(process.returncode))
            error = True
            return

    try:
        thread = Thread(target=execute)
        thread.start()
        self.stopDownload = lambda: stopping.pls_stop()
        thread.join()
    finally:
        self.stopDownload = None
        if local_playlist:
            try:
                os.unlink(local_playlist)
            except OSError:
                pass
    return not error
