import requests
import json
from streamonitor.bot import Bot


class StripChat(Bot):
    site = 'StripChat'
    siteslug = 'SC'
    aliases = ['xhamsterlive']

    def getVideoUrl(self):
        return "https://b-{server}.{host}/hls/{id}/master_{id}.m3u8".format(
                server=self.lastInfo["viewCam"]["viewServers"]["flashphoner-hls"],
                host=self.lastInfo["config"]["data"]["hlsStreamHost"],
                id=self.lastInfo["viewCam"]["streamName"]
            )

    def getStatus(self):
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:75.0) Gecko/20100101 Firefox/75.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
        }

        r = requests.get('https://hu.stripchat.com/' + self.username, headers=headers)
        if r.status_code == 404:
            return Bot.Status.NOTEXIST
        if r.status_code != 200:
            return Bot.Status.UNKNOWN

        start = b'window.__PRELOADED_STATE__ = '
        end = b'</script>'
        
        if r.content.find(start) == -1:
            return Bot.Status.OFFLINE
        
        j = r.content[r.content.find(start) + len(start):]
        j = j[:j.find(end)]
        
        try:
            self.lastInfo = json.loads(j)
        except:
            self.log('Failed to parse JSON')
            return Bot.Status.UNKNOWN

        if self.lastInfo["viewCam"]["model"]["status"] == "public" and self.lastInfo["viewCam"]["isCamAvailable"]:
            return Bot.Status.PUBLIC
        if self.lastInfo["viewCam"]["model"]["status"] in ["private", "groupShow", "p2p"]:
            return Bot.Status.PRIVATE
        if self.lastInfo["viewCam"]["model"]["status"] == "off":
            return Bot.Status.OFFLINE
        self.logger.warn(f'Got unknown status: {self.lastInfo["viewCam"]["model"]["status"]}')
        return Bot.Status.UNKNOWN


Bot.loaded_sites.add(StripChat)
