import requests
import base64
import json
from streamonitor.bot import Bot


class ManyVids(Bot):
    site = 'ManyVids'
    siteslug = 'MV'

    def __init__(self, username):
        super().__init__(username)

        self.getCookies()

    def getCookies(self):
        r = requests.get('https://www.manyvids.com/tak-live-redirect.php', allow_redirects=False)
        self.cookies.update(r.cookies)

    def getVideoUrl(self):
        r = requests.get("/".join([self.lastInfo['publicAPIURL'], self.lastInfo['floorId'], 'player-settings', self.username]), headers=self.headers, cookies=self.cookies)
        if r.cookies is None:
            return None

        self.cookies.update(r.cookies)
        params = json.loads(base64.b64decode(r.cookies.get('CloudFront-Policy').replace('_', '=')))
        url = params['Statement'][0]['Resource'][:-1] + self.username + '.m3u8'

        return self.getWantedResolutionPlaylist(url)

    def getStatus(self):
        r = requests.get('https://roompool.live.manyvids.com/roompool/' + self.username + '?private=false', headers=self.headers)
        if r.status_code != 200:
            return Bot.Status.UNKNOWN

        self.lastInfo = r.json()

        if self.lastInfo['roomLocationReason'] == "ROOM_VALIDATION_FAILED":
            return Bot.Status.NOTEXIST
        if self.lastInfo['roomLocationReason'] == "ROOM_OK":
            r = self.requestStreamInfo()
            if 'withCredentials' not in r.json():
                return Bot.Status.OFFLINE
            return Bot.Status.PUBLIC

        return Bot.Status.UNKNOWN


Bot.loaded_sites.add(ManyVids)
