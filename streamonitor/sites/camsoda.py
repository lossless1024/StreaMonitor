import requests
from streamonitor.bot import Bot


class CamSoda(Bot):
    site = 'CamSoda'
    siteslug = 'CS'

    def __init__(self, username):
        super(CamSoda, self).__init__(username)

    def getVideoUrl(self):
        v = "https://" + self.lastInfo['edge_servers'][0] + "/" + self.lastInfo['stream_name'] + \
            "_v1/index.m3u8?token=" + self.lastInfo['token']
        return self.getWantedResolutionPlaylist(v)

    def getStatus(self):
        headers = self.headers | {
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
