import subprocess
from threading import Thread
from time import sleep
from ffmpy import FFmpeg, FFRuntimeError


def getVideoFfmpeg(self, url, filename):
    ff = FFmpeg(inputs={url: None}, outputs={filename: '-c:a copy -c:v copy'})

    def execute():
        try:
            ff.run(stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FFRuntimeError as e:
            if e.exit_code and e.exit_code != 255:
                raise
        return

    process = Thread(target=execute)
    process.start()
    while not ff.process:
        sleep(1)
    self.stopDownload = ff.process.terminate
    process.join()
    self.stopDownload = None
    return True
