import requests
from streamonitor.bot import Bot
from streamonitor.downloaders.fmp4s_wss import getVideoWSSVR


class DreamCamVR(Bot):
    site = 'DreamCamVR'
    siteslug = 'DCVR'

    def __init__(self, username):
        super().__init__(username)
        self.getVideo = getVideoWSSVR
        self.stopDownloadFlag = False

    def getVideoUrl(self):
        return self.lastInfo['streamUrl']

    def getStatus(self):
        r = requests.get('https://bss.dreamcamtrue.com/api/clients/v1/broadcasts/models/' + self.username, headers=self.headers)
        if r.status_code != 200:
            return Bot.Status.UNKNOWN

        self.lastInfo = r.json()

        if self.lastInfo["broadcastStatus"] in ["public"]:
            return Bot.Status.PUBLIC
        if self.lastInfo["broadcastStatus"] in ["private"]:
            return Bot.Status.PRIVATE
        if self.lastInfo["broadcastStatus"] in ["away", "offline"]:
            return Bot.Status.OFFLINE
        self.logger.warn(f'Got unknown status: {self.lastInfo["broadcastStatus"]}')
        return Bot.Status.UNKNOWN


Bot.loaded_sites.add(DreamCamVR)
