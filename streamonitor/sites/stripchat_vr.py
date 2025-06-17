from streamonitor.enums import Status
from streamonitor.sites.stripchat import StripChat
from streamonitor.bot import Bot


class StripChatVR(StripChat):
    site = 'StripChatVR'
    siteslug = 'SCVR'

    def __init__(self, username):
        super().__init__(username)
        self.stopDownloadFlag = False
        self.vr = True
        self.url = self.getWebsiteURL()

    def getWebsiteURL(self):
        return "https://vr.stripchat.com/cam/" + self.username

    def getStatus(self):
        status = super(StripChatVR, self).getStatus()
        if status == Status.PUBLIC:
            if self.lastInfo['model']['isVr'] and type(self.lastInfo['broadcastSettings']['vrCameraSettings']) is dict:
                return Status.PUBLIC
            return Status.OFFLINE
        return status


Bot.loaded_sites.add(StripChatVR)
