import requests
from streamonitor.bot import Bot


class StripChatVR(Bot):
    site = 'StripChatVR'
    siteslug = 'SCVR'
    ModelID = ""

    def ConvertURlToVR(self, url):
        if self.ModelID == "":
            self.logger.warn(f'Unable to replace URL with VR URL: StreamID is empty')
            return None
        return url.replace(self.ModelID, self.ModelID + "_vr")


    def getVideoUrl(self):
        return self.ConvertURlToVR(self.getWantedResolutionPlaylist(None))

    def getStatus(self):
        r = requests.get('https://stripchat.com/api/vr/v2/models/username/' + self.username, headers=self.headers)
        if r.status_code != 200:
            return Bot.Status.UNKNOWN

        self.lastInfo = r.json()

        if self.ModelID == "":
            self.ModelID = self.lastInfo["cam"]["streamName"]

        if self.lastInfo['model']['isVr'] and type(self.lastInfo['broadcastSettings']['vrCameraSettings']) is dict:
            return Bot.Status.PUBLIC
        if not self.lastInfo['model']['isVr']:
            return Bot.Status.OFFLINE
        if self.lastInfo["model"]["status"] in ["private", "groupShow", "p2p", "virtualPrivate", "p2pVoice"]:
            return Bot.Status.PRIVATE
        if self.lastInfo["model"]["status"] in ["off", "idle"]:
            return Bot.Status.OFFLINE
        self.logger.warn(f'Got unknown status: {self.lastInfo["model"]["status"]}')
        return Bot.Status.UNKNOWN
    

    def getPlaylistVariants(self, url):
        def formatUrl(auto):
            return "https://edge-hls.{host}/hls/{id}/master/{id}{auto}.m3u8".format(
            server=self.lastInfo["cam"]["viewServers"]["flashphoner-hls"],
            host='doppiocdn.com',
            id=self.lastInfo["cam"]["streamName"],
            auto='_auto' if auto else '')

        variants = []
        variants.extend(super().getPlaylistVariants(formatUrl(False)))
        variants.extend(super().getPlaylistVariants(formatUrl(True)))
        return variants    



Bot.loaded_sites.add(StripChatVR)
