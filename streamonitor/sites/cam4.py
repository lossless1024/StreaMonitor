import requests
from streamonitor.bot import Bot
from streamonitor.enums import Status


class Cam4(Bot):
    site = 'Cam4'
    siteslug = 'C4'

    def getWebsiteURL(self):
        return "https://hu.cam4.com/" + self.username
    
    def getVideoUrl(self):
        if 'cdnURL' not in self.lastInfo:
            return None
        return self.getWantedResolutionPlaylist(self.lastInfo['cdnURL'])

    def getStatus(self):
        headers = self.headers | {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
        }

        if self.sc == Status.NOTRUNNING:
            r = self.session.get(f'https://hu.cam4.com/rest/v1.0/profile/{self.username}/info', headers=headers)
            if r.status_code == 403:
                return Status.RESTRICTED
            elif r.status_code != 200:
                return Status.NOTEXIST

            r = r.json()
            if not r['online']:
                return Status.OFFLINE

        r = self.session.get(f'https://webchat.cam4.com/requestAccess?roomname={self.username}', headers=headers)
        if r.status_code != 200:
            return Status.UNKNOWN
        r = r.json()
        if r.get('privateStream', False):
            return Status.PRIVATE

        r = self.session.get(f'https://hu.cam4.com/rest/v1.0/profile/{self.username}/streamInfo', headers=headers)
        if r.status_code == 204:
            return Status.OFFLINE
        elif r.status_code == 200:
            self.lastInfo = r.json()
            return Status.PUBLIC

        return Status.UNKNOWN
