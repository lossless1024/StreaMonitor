import requests
from streamonitor.bot import Bot
from streamonitor.downloaders.ffmpeg import getVideoFfmpeg


class CamSoda(Bot):
    site = 'CamSoda'
    siteslug = 'CS'

    def __init__(self, username):
        super(CamSoda, self).__init__(username)
        self.getVideo = getVideoFfmpeg

    def getVideoUrl(self):
        v = "https://" + self.lastInfo['edge_servers'][0] + "/" + self.lastInfo['stream_name'] + \
            "_v1/index.m3u8?token=" + self.lastInfo['token']

        v = "https://" + self.lastInfo['edge_servers'][0] + "/" + self.lastInfo['stream_name'] + \
            "_v1/" + requests.get(v).content.split(b'\n')[-2].decode('ascii')

        return v

    def getStatus(self):
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:75.0) Gecko/20100101 Firefox/75.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
        }

        r = requests.get('https://www.camsoda.com/api/v1/video/vtoken/' + self.username, headers=headers)
        if r.status_code != 200:
            return Bot.Status.UNKNOWN

        self.lastInfo = r.json()

        if "message" in self.lastInfo and self.lastInfo["message"] == "No broadcaster found":
            return Bot.Status.NOTEXIST
        elif "edge_servers" in self.lastInfo and len(self.lastInfo["edge_servers"]) > 0:
            return Bot.Status.PUBLIC
        elif "private_servers" in self.lastInfo and len(self.lastInfo["private_servers"]) > 0:
            return Bot.Status.PRIVATE
        elif "token" in self.lastInfo:
            return Bot.Status.OFFLINE
        return Bot.Status.UNKNOWN


Bot.loaded_sites.add(CamSoda)
