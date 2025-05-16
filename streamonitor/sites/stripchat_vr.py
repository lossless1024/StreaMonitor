from streamonitor.bot import Bot
from streamonitor.sites.stripchat import StripChat


class StripChatVR(StripChat):
    site = 'StripChatVR'
    siteslug = 'SCVR'

    def __init__(self, username):
        super().__init__(username)
        self.stopDownloadFlag = False
        self.vr = True

    def getWebsiteURL(self):
        return "https://vr.stripchat.com/cam/" + self.username

    def getStatus(self):
        status = super(StripChatVR, self).getStatus()
        if status == Bot.Status.PUBLIC:
            if self.lastInfo['model']['isVr'] and type(self.lastInfo['broadcastSettings']['vrCameraSettings']) is dict:
                return Bot.Status.PUBLIC
            return Bot.Status.OFFLINE
        return status

    def vrFilenamePart(self):
        vr_cam_settings = self.lastInfo['broadcastSettings']['vrCameraSettings']
        return f"_{vr_cam_settings["stereoPacking"]}_{self.frame_format_map[vr_cam_settings["frameFormat"]]}{vr_cam_settings["horizontalAngle"]}"


Bot.loaded_sites.add(StripChatVR)
