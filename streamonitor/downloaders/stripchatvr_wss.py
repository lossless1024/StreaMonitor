import json
import os
import subprocess
from threading import Thread
from websocket import create_connection, WebSocketConnectionClosedException, WebSocketException
from contextlib import closing
from ffmpy import FFmpeg, FFRuntimeError


def getVideoWSSVR(self, url, filename):
    self.stopDownloadFlag = False
    tmpfilename = filename[:-len('.mp4')] + '.tmp.mp4'

    def execute():
        with open(tmpfilename, 'ab') as outfile:
            while not self.stopDownloadFlag:
                try:
                    with closing(create_connection(url, timeout=10)) as conn:
                        conn.send('{"url":"stream/hello","version":"0.0.1"}')
                        while not self.stopDownloadFlag:
                            t = conn.recv()
                            try:
                                tj = json.loads(t)
                                if 'url' in tj:
                                    if tj['url'] == 'stream/qual':
                                        conn.send('{"quality":"test","url":"stream/play","version":"0.0.1"}')
                                        break
                                if 'message' in tj:
                                    if tj['message'] == 'ping':
                                        return False
                            except:
                                return False

                        while not self.stopDownloadFlag:
                            outfile.write(conn.recv())
                except WebSocketConnectionClosedException:
                    self.log('WebSocket connection closed')
                    continue
                except WebSocketException:
                    return False

    def terminate():
        self.stopDownloadFlag = True

    process = Thread(target=execute)
    process.start()
    self.stopDownload = terminate
    process.join()
    self.stopDownload = None

    # Post-processing
    try:
        ff = FFmpeg(inputs={tmpfilename: '-ignore_editlist 1'}, outputs={filename: '-codec copy'})
        ff.run(stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FFRuntimeError as e:
        if e.exit_code and e.exit_code != 255:
            return False

    os.remove(tmpfilename)
    return True
