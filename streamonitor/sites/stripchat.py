import requests
from streamonitor.bot import Bot


class StripChat(Bot):
    site = 'StripChat'
    siteslug = 'SC'

    def getVideoUrl(self):
        return self.getWantedResolutionPlaylist(None)

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

    def getStatus(self):
        r = requests.get('https://stripchat.com/api/vr/v2/models/username/' + self.username, headers=self.headers)
        if r.status_code != 200:
            return Bot.Status.UNKNOWN

        self.lastInfo = r.json()

        if self.lastInfo["model"]["status"] == "public" and self.lastInfo["isCamAvailable"] and self.lastInfo['cam']["isCamActive"]:
            return Bot.Status.PUBLIC
        if self.lastInfo["model"]["status"] in ["private", "groupShow", "p2p", "virtualPrivate", "p2pVoice"]:
            return Bot.Status.PRIVATE
        if self.lastInfo["model"]["status"] in ["off", "idle"]:
            return Bot.Status.OFFLINE
        self.logger.warn(f'Got unknown status: {self.lastInfo["model"]["status"]}')
        return Bot.Status.UNKNOWN


Bot.loaded_sites.add(StripChat)
