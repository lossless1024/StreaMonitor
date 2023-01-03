import requests
from streamonitor.bot import Bot


class Cam4(Bot):
    site = 'Cam4'
    siteslug = 'C4'

    def getVideoUrl(self):
        return self.getWantedResolutionPlaylist(self.lastInfo['cdnURL'])

    def getStatus(self):
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:75.0) Gecko/20100101 Firefox/75.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
        }

        if self.sc == self.Status.NOTRUNNING:
            r = requests.get(f'https://hu.cam4.com/rest/v1.0/profile/{self.username}/info', headers=headers)
            if r.status_code != 200:
                return Bot.Status.NOTEXIST

            r = r.json()
            if not r['online']:
                return Bot.Status.OFFLINE

        r = requests.get(f'https://webchat.cam4.com/requestAccess?roomname={self.username}', headers=headers)
        if r.status_code != 200:
            return Bot.Status.UNKNOWN
        r = r.json()
        if r.get('privateStream', False):
            return Bot.Status.PRIVATE

        r = requests.get(f'https://hu.cam4.com/rest/v1.0/profile/{self.username}/streamInfo', headers=headers)
        if r.status_code == 204:
            return Bot.Status.OFFLINE
        elif r.status_code == 200:
            self.lastInfo = r.json()
            return Bot.Status.PUBLIC

        return Bot.Status.UNKNOWN


Bot.loaded_sites.add(Cam4)
