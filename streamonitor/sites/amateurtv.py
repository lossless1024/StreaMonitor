import requests
from streamonitor.bot import Bot


class AmateurTV(Bot):
    site = 'AmateurTV'
    siteslug = 'ATV'

    def getPlaylistVariants(self, url):
        sources = []
        for resolution in self.lastInfo['qualities']:
            width, height = resolution.split('x')
            sources.append(( f"{self.lastInfo['videoTechnologies']['fmp4']}&variant={height}", (int(width), int(height)) ))
        return sources

    def getVideoUrl(self):
        return self.getWantedResolutionPlaylist(None)

    def getStatus(self):
        headers = self.headers | {
            'Content-Type': 'application/json',
            'Referer': 'https://amateur.tv/'
        }
        r = requests.get(f'https://www.amateur.tv/v3/readmodel/show/{self.username}/en', headers=headers)

        if r.status_code != 200:
            return Bot.Status.UNKNOWN

        self.lastInfo = r.json()

        if self.lastInfo.get('message') == 'NOT_FOUND':
            return Bot.Status.NOTEXIST
        if self.lastInfo.get('result') == 'KO':
            return Bot.Status.UNKNOWN
        if self.lastInfo.get('status') == 'online':
            if self.lastInfo.get('privateChatStatus') is None:
                return Bot.Status.PUBLIC
            else:
                return Bot.Status.PRIVATE
        if self.lastInfo.get('status') == 'offline':
            return Bot.Status.OFFLINE


Bot.loaded_sites.add(AmateurTV)
