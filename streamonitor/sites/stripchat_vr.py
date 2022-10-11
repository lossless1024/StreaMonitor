import json
from threading import Thread

from websocket import create_connection, WebSocketConnectionClosedException, WebSocketException
from contextlib import closing

from streamonitor.sites.stripchat import StripChat
from streamonitor.bot import Bot


class StripChatVR(StripChat):
    site = 'StripChatVR'
    siteslug = 'SCVR'

    def __init__(self, username):
        super().__init__(username)
        self.getVideo = self.getVideoWSSVR
        self.stopDownloadFlag = False

    @staticmethod
    def getVideoWSSVR(self, url, filename):
        self.stopDownloadFlag = False

        def execute():
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

                    with open(filename, 'wb') as outfile:
                        while not self.stopDownloadFlag:
                            outfile.write(conn.recv())
            except WebSocketConnectionClosedException:
                self.log('Show ended (WebSocket connection closed)')
                return True
            except WebSocketException:
                return False

        def terminate():
            self.stopDownloadFlag = True

        process = Thread(target=execute)
        process.start()
        self.stopDownload = terminate
        process.join()
        self.stopDownload = None
        return True

    def getVideoUrl(self):
        return "wss://s-{server}.{host}/{id}_vr_webxr?".format(
            server=self.lastInfo["broadcastSettings"]["vrBroadcastServer"],
            host='stripcdn.com',
            id=self.lastInfo["cam"]["streamName"]
        ) + '&'.join([k + '=' + v for k, v in self.lastInfo['broadcastSettings']['vrCameraSettings'].items()])

    def getStatus(self):
        status = super(StripChatVR, self).getStatus()
        if status == Bot.Status.PUBLIC and self.lastInfo['model']['isVr']:
            return status
        return Bot.Status.OFFLINE


Bot.loaded_sites.add(StripChatVR)
