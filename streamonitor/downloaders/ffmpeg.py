import errno
import subprocess
from threading import Thread
from parameters import DEBUG


def getVideoFfmpeg(self, url, filename):
    cmd = [
        'ffmpeg',
        '-user_agent', self.headers['User-Agent'],
        '-i', url,
        '-c:a', 'copy',
        '-c:v', 'copy',
        filename
    ]

    class _Stopper:
        def __init__(self):
            self.stop = False

        def pls_stop(self):
            self.stop = True

    stopping = _Stopper()

    def execute():
        try:
            stdout = open(filename + '.stdout.log', 'w+') if DEBUG else subprocess.DEVNULL
            stderr = open(filename + '.stderr.log', 'w+') if DEBUG else subprocess.DEVNULL
            process = subprocess.Popen(args=cmd, stdin=subprocess.PIPE, stderr=stderr, stdout=stdout)
        except OSError as e:
            if e.errno == errno.ENOENT:
                self.logger.error('FFMpeg executable not found!')
                return
            else:
                raise

        while process.poll() is None:
            if stopping.stop:
                process.communicate(b'q')
                break
            try:
                process.wait(1)
            except subprocess.TimeoutExpired:
                pass

        if process.returncode and process.returncode != 0 and process.returncode != 255:
            raise

    thread = Thread(target=execute)
    thread.start()
    self.stopDownload = lambda: stopping.pls_stop()
    thread.join()
    self.stopDownload = None
    return True
