import requests
import json
from streamonitor.bot import Bot


class StripChat(Bot):
    site = 'StripChat'
    siteslug = 'SC'

    def getVideoUrl(self):
        return "https://b-{server}.{host}/hls/{id}/master_{id}.m3u8".format(
                server=self.lastInfo["cam"]["viewServers"]["flashphoner-hls"],
                host='doppiocdn.com',
                id=self.lastInfo["cam"]["streamName"]
            )

    def getStatus(self):
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:75.0) Gecko/20100101 Firefox/75.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
        }

        r = requests.get('https://stripchat.com/api/vr/v2/models/username/' + self.username, headers=headers)
        if r.status_code != 200:
            return Bot.Status.UNKNOWN

        self.lastInfo = r.json()

        if self.lastInfo["model"]["status"] == "public" and self.lastInfo["isCamAvailable"] and self.lastInfo['cam']["isCamActive"]:
            return Bot.Status.PUBLIC
        if self.lastInfo["model"]["status"] in ["private", "groupShow", "p2p"]:
            return Bot.Status.PRIVATE
        if self.lastInfo["model"]["status"] in ["off", "idle"]:
            return Bot.Status.OFFLINE
        self.logger.warn(f'Got unknown status: {self.lastInfo["model"]["status"]}')
        return Bot.Status.UNKNOWN


Bot.loaded_sites.add(StripChat)
