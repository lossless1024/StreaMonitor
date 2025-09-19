import m3u8
import os
import subprocess
from threading import Thread
from ffmpy import FFmpeg, FFRuntimeError
from time import sleep
from parameters import DEBUG, CONTAINER, SEGMENT_TIME, FFMPEG_PATH
import re
from datetime import datetime, timedelta

_http_lib = None
if not _http_lib:
    try:
        import pycurl_requests as requests

        _http_lib = "pycurl"
    except ImportError:
        pass
if not _http_lib:
    try:
        import requests

        _http_lib = "requests"
    except ImportError:
        pass
if not _http_lib:
    raise ImportError("Please install requests or pycurl package to proceed")


def getVideoNativeHLS(self, url, filename, m3u_processor=None):
    self.stopDownloadFlag = False
    error = False
    tmpfilename = filename[: -len("." + CONTAINER)] + ".tmp.ts"
    session = requests.Session()

    def execute():
        nonlocal error
        downloaded_list = []
        with open(tmpfilename, "wb") as outfile:
            did_download = False
            while not self.stopDownloadFlag:
                r = session.get(url, headers=self.headers, cookies=self.cookies)
                content = r.content.decode("utf-8")
                if m3u_processor:
                    content = m3u_processor(content)
                chunklist = m3u8.loads(content)
                if len(chunklist.segments) == 0:
                    return
                for chunk in chunklist.segment_map + chunklist.segments:
                    if chunk.uri in downloaded_list:
                        continue
                    did_download = True
                    downloaded_list.append(chunk.uri)
                    chunk_uri = chunk.uri
                    self.debug("Downloading " + chunk_uri)
                    if not chunk_uri.startswith("https://"):
                        chunk_uri = (
                            "/".join(url.split(".m3u8")[0].split("/")[:-1])
                            + "/"
                            + chunk_uri
                        )
                    m = session.get(
                        chunk_uri, headers=self.headers, cookies=self.cookies
                    )
                    if m.status_code != 200:
                        return
                    outfile.write(m.content)
                    if self.stopDownloadFlag:
                        return
                if not did_download:
                    sleep(10)

    def terminate():
        self.stopDownloadFlag = True

    process = Thread(target=execute)
    process.start()
    self.stopDownload = terminate
    process.join()
    self.stopDownload = None

    # if error:
    #     return False

    if not os.path.exists(tmpfilename):
        return False

    if os.path.getsize(tmpfilename) == 0:
        os.remove(tmpfilename)
        return False

    # Post-processing
    try:
        stdout = (
            open(filename + ".postprocess_stdout.log", "w+")
            if DEBUG
            else subprocess.DEVNULL
        )
        stderr = (
            open(filename + ".postprocess_stderr.log", "w+")
            if DEBUG
            else subprocess.DEVNULL
        )
        output_str = "-c:a copy -c:v copy"
        if SEGMENT_TIME is not None:
            output_str += (
                f" -f segment -reset_timestamps 1 -segment_time {str(SEGMENT_TIME)}"
            )
            filename = filename[: -len("." + CONTAINER)] + "_%03d." + CONTAINER
        ff = FFmpeg(
            executable=FFMPEG_PATH,
            inputs={tmpfilename: None},
            outputs={filename: output_str},
        )
        ff.run(stdout=stdout, stderr=stderr)
        os.remove(tmpfilename)
    except FFRuntimeError as e:
        if e.exit_code and e.exit_code != 255:
            return False

    # -------- Move processed file(s) --------
    import shutil
    from datetime import datetime

    today_str = datetime.now().strftime("%Y%m%d")
    target_dir = f"/Volumes/T7 2TB/opnemen/klaar/{today_str}"
    os.makedirs(target_dir, exist_ok=True)

    if SEGMENT_TIME is not None:
        import glob

        segment_pattern = filename[: -len("_%03d." + CONTAINER)] + "_*." + CONTAINER
        for segfile in glob.glob(segment_pattern):
            shutil.move(segfile, os.path.join(target_dir, os.path.basename(segfile)))
    else:

        # Match pattern
        pattern = re.compile(
            r"^(.*?)-(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})\.mkv$"
        )
        match = pattern.match(filename)

        if match:
            prefix, year, month, day, hour, minute, second = match.groups()

            # Build datetime object
            dt = datetime(
                int(year), int(month), int(day), int(hour), int(minute), int(second)
            )

            # Example adjustment (customize as needed)
            dt = dt - timedelta(hours=3) + timedelta(seconds=11)

            # New name
            newFilename = f"{prefix}_{dt.strftime('%Y-%m-%d_%H-%M-%S')}_Stripchat.mkv"

            shutil.move(
                filename, os.path.join(target_dir, os.path.basename(newFilename))
            )

        else:
            print("Filename does not match expected pattern.")

            shutil.move(filename, os.path.join(target_dir, os.path.basename(filename)))

    return True


# ...existing code...
