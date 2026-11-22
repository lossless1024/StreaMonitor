import m3u8
import os
import subprocess
from threading import Thread
from urllib.parse import urljoin
from ffmpy import FFmpeg, FFRuntimeError
from time import sleep
from parameters import DEBUG, CONTAINER, SEGMENT_TIME, FFMPEG_PATH

_http_lib = None
if not _http_lib:
    try:
        import pycurl_requests as requests
        _http_lib = 'pycurl'
    except ImportError:
        pass
if not _http_lib:
    try:
        import requests
        _http_lib = 'requests'
    except ImportError:
        pass
if not _http_lib:
    raise ImportError("Please install requests or pycurl package to proceed")


def getVideoNativeHLS(self, url, filename, m3u_processor=None):
    self.stopDownloadFlag = False
    error = False
    tmpfilename = filename[:-len('.' + CONTAINER)] + '.tmp.ts'
    os.makedirs(os.path.dirname(tmpfilename) or '.', exist_ok=True)
    session = requests.Session()

    def execute():
        nonlocal error
        downloaded_list: set[str] = set()
        try:
            with open(tmpfilename, 'wb') as outfile:
                did_download = False
                while not self.stopDownloadFlag:
                    r = session.get(
                        url,
                        headers=self.headers,
                        cookies=self.cookies,
                        timeout=10,
                    )
                    if r.status_code != 200:
                        error = True
                        return
                    content = r.content.decode("utf-8")
                    if m3u_processor:
                        content = m3u_processor(content)
                        if content is None:
                            error = True
                            return
                    chunklist = m3u8.loads(content)
                    if len(chunklist.segments) == 0:
                        return
                    all_segments = chunklist.segment_map + chunklist.segments
                    chunks = [
                        chunk.uri for chunk in all_segments
                        if chunk.uri and chunk.uri not in downloaded_list
                    ]
                    if not chunks:
                        sleep(1)
                    for chunk_uri in chunks:
                        did_download = True
                        downloaded_list.add(chunk_uri)
                        self.debug('Downloading ' + chunk_uri)
                        chunk_url = urljoin(url, chunk_uri)
                        m = session.get(
                            chunk_url,
                            headers=self.headers,
                            cookies=self.cookies,
                            timeout=10,
                        )
                        if m.status_code != 200:
                            error = True
                            return
                        outfile.write(m.content)
                        if self.stopDownloadFlag:
                            return
                    if not did_download:
                        sleep(10)
        except Exception as download_error:
            error = True
            try:
                self.logger.warning(
                    "Native HLS downloader failed: %s",
                    download_error,
                )
            except Exception:
                pass

    def terminate():
        self.stopDownloadFlag = True

    process = Thread(target=execute)
    process.start()
    self.stopDownload = terminate
    process.join()
    self.stopDownload = None

    if error:
        return False

    if not os.path.exists(tmpfilename):
        return False

    if os.path.getsize(tmpfilename) == 0:
        os.remove(tmpfilename)
        return False

    # Post-processing
    output_path = filename
    try:
        stdout = open(filename + '.postprocess_stdout.log', 'w+') if DEBUG else subprocess.DEVNULL
        stderr = open(filename + '.postprocess_stderr.log', 'w+') if DEBUG else subprocess.DEVNULL
        output_str = '-c:a copy -c:v copy'
        suffix = ''
        if SEGMENT_TIME is not None:
            output_str += f' -f segment -reset_timestamps 1 -segment_time {str(SEGMENT_TIME)}'
            if hasattr(self, 'filename_extra_suffix'):
                suffix = self.filename_extra_suffix
            output_path = filename[:-len('.' + CONTAINER)] + '_%03d' + suffix + '.' + CONTAINER
        ff = FFmpeg(executable=FFMPEG_PATH, inputs={tmpfilename: None}, outputs={output_path: output_str})
        ff.run(stdout=stdout, stderr=stderr)
    except FFRuntimeError as e:
        if e.exit_code and e.exit_code != 255:
            return False
        # 255 means ffmpeg was killed, usually by a stop request or a
        # shutdown. The temp file still holds every downloaded segment, so it
        # is kept for recoverOrphanedRecordings() instead of being discarded.
        if SEGMENT_TIME is not None:
            return True
        return os.path.exists(output_path) and os.path.getsize(output_path) > 0

    # The remux succeeded, so the raw segments are no longer needed.
    try:
        os.remove(tmpfilename)
    except OSError:
        pass
    return True
