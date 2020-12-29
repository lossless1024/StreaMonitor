import requests
import bot


class PornHubLive(bot.Bot):
    site = 'PornHubLive'
    siteslug = 'PHL'

    def __init__(self, username):
        super().__init__(username)
        self.lastInfo = None

    def getVideoUrl(self):
        # formats: mp4-rtmp, mp4-hls, mp4-ws
        return self.lastInfo['formats']['mp4-hls']['encodings'][2]['location'] or None

    def getStatus(self):
        headers = {
            'Content-Type': 'application/json',
            'Referer': 'https://www.pornhublive.com/'
        }
        r = requests.get('https://manifest-server.naiadsystems.com/live/s:' + self.username + '.json?last=load&format=mp4-hls',
                         headers=headers)

        if r.status_code == 200:
            self.lastInfo = r.json()
        return bot.Bot.Status(r.status_code)
