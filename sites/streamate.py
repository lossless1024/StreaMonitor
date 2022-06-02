import requests
from bot import Bot


class StreaMate(Bot):
    site = 'StreaMate'
    siteslug = 'SM'
    aliases = ['pornhublive']

    def getVideoUrl(self):
        # formats: mp4-rtmp, mp4-hls, mp4-ws
        return self.lastInfo['formats']['mp4-hls']['encodings'][2]['location'] or None

    def getStatus(self):
        headers = {
            'Content-Type': 'application/json',
            'Referer': 'https://streamate.com/'
        }
        r = requests.get('https://manifest-server.naiadsystems.com/live/s:' + self.username + '.json?last=load&format=mp4-hls',
                         headers=headers)

        if r.status_code == 200:
            self.lastInfo = r.json()
        return Bot.Status(r.status_code)


Bot.loaded_sites.add(StreaMate)
