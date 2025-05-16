import m3u8
import os
import requests
import subprocess
from threading import Thread
from ffmpy import FFmpeg, FFRuntimeError
from time import sleep
from parameters import DEBUG, CONTAINER, SEGMENT_TIME
from streamonitor.bot import Bot


def getVideoNativeHLS(self: Bot):
    self.stopDownloadFlag = False
    error = False
    tmpfilename = self.filename()[:-len('.' + CONTAINER)] + '.tmp.ts'

    def debug_(message):
        self.debug(message, filename + '.log')

    def execute():
        nonlocal error
        downloaded_list = []
        with open(tmpfilename, 'wb') as outfile:
            did_download = False
            while not self.stopDownloadFlag:
                r = requests.get(self.getVideoUrl(), headers=self.headers, cookies=self.cookies)
                chunklist = m3u8.loads(r.content.decode("utf-8"))
                if len(chunklist.segments) == 0:
                    return
                for chunk in chunklist.segments:
                    if chunk.uri in downloaded_list:
                        continue
                    did_download = True
                    downloaded_list.append(chunk.uri)
                    chunk_uri = chunk.uri
                    debug_('Downloading ' + chunk_uri)
                    if not chunk_uri.startswith("https://"):
                        chunk_uri = '/'.join(self.getVideoUrl().split('.m3u8')[0].split('/')[:-1]) + '/' + chunk_uri
                    m = requests.get(chunk_uri, headers=self.headers, cookies=self.cookies)
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

    if error:
        return False

    # Post-processing
    try:
        stdout = open(self.filename() + '.postprocess_stdout.log', 'w+') if DEBUG else subprocess.DEVNULL
        stderr = open(self.filename() + '.postprocess_stderr.log', 'w+') if DEBUG else subprocess.DEVNULL
        output_str = '-c:a copy -c:v copy'
        if SEGMENT_TIME is not None:
            output_str += f' -f segment -reset_timestamps 1 -segment_time {str(SEGMENT_TIME)}',
            filename = self.filename()[:-len('.' + CONTAINER)] + '_%03d.' + CONTAINER
        ff = FFmpeg(inputs={tmpfilename: None}, outputs={self.filename(): output_str})
        ff.run(stdout=stdout, stderr=stderr)
        os.remove(tmpfilename)
    except FFRuntimeError as e:
        if e.exit_code and e.exit_code != 255:
            return False

    return True
