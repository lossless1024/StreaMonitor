import subprocess
from ffmpy import FFmpeg, FFRuntimeError


def getVideoFfmpeg(self, url):
    self.log("Started downloading show")
    filename = self.genOutFilename()
    ff = FFmpeg(inputs={url: None}, outputs={filename: '-c:a copy -c:v copy'})
    try:
        ff.run(stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FFRuntimeError:
        self.sc = self.Status.ERROR
        self.log("Error while downloading")
