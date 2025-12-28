import requests
from streamonitor.bot import Bot
from streamonitor.enums import Status


class StreaMate(Bot):
    site = 'StreaMate'
    siteslug = 'SM'
    aliases = ['pornhublive']

    def getWebsiteURL(self):
        return "https://streamate.com/cam/" + self.username

    def getPlaylistVariants(self, url):
        sources = []
        # formats: mp4-rtmp, mp4-hls, mp4-ws
        for source in self.lastInfo['formats']['mp4-hls']['encodings']:
            sources.append({
                'url': source['location'],
                'resolution': (source['videoWidth'], source['videoHeight']),
                'frame_rate': None,
                'bandwidth': None
            })
        return sources

    def getVideoUrl(self):
        return self.getWantedResolutionPlaylist(None)

    def getStatus(self):
        headers = self.headers | {
            'Content-Type': 'application/json',
            'Referer': 'https://streamate.com/'
        }
        r = self.session.get('https://manifest-server.naiadsystems.com/live/s:' + self.username + '.json?last=load&format=mp4-hls',
                         headers=headers)

        if r.status_code == 200:
            self.lastInfo = r.json()
        return Status(r.status_code)
