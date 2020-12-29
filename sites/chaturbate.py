import requests
import bot


class Chaturbate(bot.Bot):
    site = 'Chaturbate'
    siteslug = 'CB'

    def __init__(self, username):
        super().__init__(username)
        self.sleep_on_offline = 30
        self.sleep_on_error = 60

    def getVideoUrl(self):
        return "https://chaturbate.com/{}/".format(self.username)

    def getStatus(self):
        headers = {"X-Requested-With": "XMLHttpRequest"}
        data = {"room_slug": self.username, "bandwidth": "high"}

        try:
            r = requests.post("https://chaturbate.com/get_edge_hls_url_ajax/", headers=headers, data=data)
            if r.json()["room_status"] == "public":
                self.ratelimit = False
                return self.Status.PUBLIC
            self.ratelimit = False
            return self.Status.OFFLINE

        except Exception as e:
            self.ratelimit = True
            return self.Status.RATELIMIT
