from streamonitor.sites.stripchat import StripChat
from streamonitor.bot import Bot


class StripChatVR(StripChat):
    site = 'StripChatVR'
    siteslug = 'SCVR'

    def __init__(self, username):
        super().__init__(username)
        self.stopDownloadFlag = False
        self.vr = True

    def getStatus(self):
        status = super(StripChatVR, self).getStatus()
        if status == Bot.Status.PUBLIC:
            if self.lastInfo['model']['isVr'] and type(self.lastInfo['broadcastSettings']['vrCameraSettings']) is dict:
                return Bot.Status.PUBLIC
            return Bot.Status.OFFLINE
        return status


Bot.loaded_sites.add(StripChatVR)
