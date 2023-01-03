import requests
from streamonitor.bot import Bot


class StreaMate(Bot):
    site = 'StreaMate'
    siteslug = 'SM'
    aliases = ['pornhublive']

    def getPlaylistVariants(self, url):
        sources = []
        # formats: mp4-rtmp, mp4-hls, mp4-ws
        for source in self.lastInfo['formats']['mp4-hls']['encodings']:
            sources.append(( source['location'], (source['videoWidth'], source['videoHeight']) ))
        return sources

    def getVideoUrl(self):
        return self.getWantedResolutionPlaylist(None)

    def getStatus(self):
        headers = self.headers | {
            'Content-Type': 'application/json',
            'Referer': 'https://streamate.com/'
        }
        r = requests.get('https://manifest-server.naiadsystems.com/live/s:' + self.username + '.json?last=load&format=mp4-hls',
                         headers=headers)

        if r.status_code == 200:
            self.lastInfo = r.json()
        return Bot.Status(r.status_code)


Bot.loaded_sites.add(StreaMate)
