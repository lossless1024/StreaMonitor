import requests
import json
from bot import Bot


class StripChat(Bot):
    site = 'StripChat'
    siteslug = 'SC'
    aliases = ['xhamsterlive']

    def __init__(self, username):
        super().__init__(username)
        self.info = None
        self.getInfo()

    def getVideoUrl(self):
        return "https://b-{server}.stripst.com/hls/{id}/master_{id}.m3u8".format(
                server=self.info["viewServers"]["flashphoner-hls"],
                id=self.info["model"]["id"]
            ) or None

    def getInfo(self):
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
        j = r.content[r.content.find(start) + len(start):]
        j = j[:j.find(end)]
        self.info = json.loads(j)["viewCam"]

        if self.info["model"]["status"] == "public":
            return Bot.Status.PUBLIC
        if self.info["model"]["status"] == "private":
            return Bot.Status.PRIVATE
        if self.info["model"]["status"] == "off":
            return Bot.Status.OFFLINE
        return Bot.Status.UNKNOWN

    def getStatus(self):
        r = requests.get(self.getVideoUrl())
        return Bot.Status(r.status_code)


Bot.loaded_sites.add(StripChat)
