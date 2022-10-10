import requests
from streamonitor.bot import Bot
from streamonitor.downloaders.youtubedl import getVideoYtdl


class Chaturbate(Bot):
    site = 'Chaturbate'
    siteslug = 'CB'

    def __init__(self, username):
        super().__init__(username)
        self.getVideo = getVideoYtdl
        self.sleep_on_offline = 30
        self.sleep_on_error = 60

    def getVideoUrl(self):
        return f'https://chaturbate.com/{self.username}/'

    def getStatus(self):
        headers = {"X-Requested-With": "XMLHttpRequest"}
        data = {"room_slug": self.username, "bandwidth": "high"}

        try:
            r = requests.post("https://chaturbate.com/get_edge_hls_url_ajax/", headers=headers, data=data)
            if r.json()["room_status"] == "public":
                status = self.Status.PUBLIC
            elif r.json()["room_status"] in ["private", "hidden"]:
                status = self.Status.PRIVATE
            else:
                status = self.Status.OFFLINE
        except Exception as e:
            status = self.Status.RATELIMIT

        self.ratelimit = status == self.Status.RATELIMIT
        return status


Bot.loaded_sites.add(Chaturbate)
