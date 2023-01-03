from streamonitor.sites.stripchat import StripChat
from streamonitor.bot import Bot
from streamonitor.downloaders.fmp4s_wss import getVideoWSSVR


class StripChatVR(StripChat):
    site = 'StripChatVR'
    siteslug = 'SCVR'

    def __init__(self, username):
        super().__init__(username)
        self.getVideo = getVideoWSSVR
        self.stopDownloadFlag = False

    def getVideoUrl(self):
        return "wss://s-{server}.{host}/{id}_vr_webxr?".format(
            server=self.lastInfo["broadcastSettings"]["vrBroadcastServer"],
            host='stripcdn.com',
            id=self.lastInfo["cam"]["streamName"]
        ) + '&'.join([k + '=' + v for k, v in self.lastInfo['broadcastSettings']['vrCameraSettings'].items()])

    def getStatus(self):
        status = super(StripChatVR, self).getStatus()
        if status == Bot.Status.PUBLIC:
            if self.lastInfo['model']['isVr'] and type(self.lastInfo['broadcastSettings']['vrCameraSettings']) is dict:
                return Bot.Status.PUBLIC
            return Bot.Status.OFFLINE
        return status


Bot.loaded_sites.add(StripChatVR)
