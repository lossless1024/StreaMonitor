import requests
from streamonitor.bot import Bot
from streamonitor.enums import Status


class AmateurTV(Bot):
    site = 'AmateurTV'
    siteslug = 'ATV'

    def getPlaylistVariants(self, url):
        sources = []
        for resolution in self.lastInfo['qualities']:
            width, height = resolution.split('x')
            sources.append({
                'url': f"{self.lastInfo['videoTechnologies']['fmp4']}&variant={height}",
                'resolution': (int(width), int(height)),
                'frame_rate': None,
                'bandwidth': None
            })
        return sources

    def getVideoUrl(self):
        return self.getWantedResolutionPlaylist(None)

    def getStatus(self):
        headers = self.headers | {
            'Content-Type': 'application/json',
            'Referer': 'https://amateur.tv/'
        }
        r = self.session.get(f'https://www.amateur.tv/v3/readmodel/show/{self.username}/en', headers=headers)

        if r.status_code != 200:
            return Status.UNKNOWN

        self.lastInfo = r.json()

        if self.lastInfo.get('message') == 'NOT_FOUND':
            return Status.NOTEXIST
        if self.lastInfo.get('result') == 'KO':
            return Status.UNKNOWN
        if self.lastInfo.get('status') == 'online':
            if self.lastInfo.get('privateChatStatus') is None:
                return Status.PUBLIC
            else:
                return Status.PRIVATE
        if self.lastInfo.get('status') == 'offline':
            return Status.OFFLINE
        return Status.UNKNOWN
