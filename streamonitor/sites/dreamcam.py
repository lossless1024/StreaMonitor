import requests

from streamonitor.bot import Bot
from streamonitor.enums import Status


class DreamCam(Bot):
    site = 'DreamCam'
    siteslug = 'DC'

    _stream_type = 'video2D'

    def getVideoUrl(self):
        for stream in self.lastInfo['streams']:
            if stream['streamType'] == self._stream_type:
                if stream['status'] == 'online':
                    return stream['url']
        return None

    def getStatus(self):
        r = self.session.get('https://bss.dreamcamtrue.com/api/clients/v1/broadcasts/models/' + self.username, headers=self.headers)
        if r.status_code != 200:
            return Status.UNKNOWN

        self.lastInfo = r.json()

        if self.lastInfo["broadcastStatus"] in ["public"]:
            return Status.PUBLIC
        if self.lastInfo["broadcastStatus"] in ["private"]:
            return Status.PRIVATE
        if self.lastInfo["broadcastStatus"] in ["away", "offline"]:
            return Status.OFFLINE
        self.logger.warn(f'Got unknown status: {self.lastInfo["broadcastStatus"]}')
        return Status.UNKNOWN
