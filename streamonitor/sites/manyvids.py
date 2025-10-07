import base64
import json
import requests
from requests.cookies import RequestsCookieJar
from streamonitor.bot import Bot
from streamonitor.downloaders.hls import getVideoNativeHLS
from streamonitor.enums import Status


class ManyVids(Bot):
    site = 'ManyVids'
    siteslug = 'MV'

    def __init__(self, username):
        super().__init__(username)
        self.getVideo = getVideoNativeHLS
        self.stopDownloadFlag = False
        self.cookies = RequestsCookieJar()
        self.cookieUpdater = self.updateMediaCookies
        self.cookie_update_interval = 120
        self.updateSiteCookies()

    def requestStreamInfo(self):
        r = requests.get("/".join([self.lastInfo['publicAPIURL'], self.lastInfo['floorId'], 'player-settings', self.username]), headers=self.headers, cookies=self.cookies)
        if r.cookies is not None:
            self.cookies.update(r.cookies)
        return r

    def updateMediaCookies(self):
        r = self.requestStreamInfo()
        return r.cookies is not None

    def updateSiteCookies(self):
        r = requests.get('https://www.manyvids.com/tak-live-redirect.php', allow_redirects=False)
        self.cookies.update(r.cookies)

    def getVideoUrl(self):
        r = self.requestStreamInfo()
        params = json.loads(base64.b64decode(r.cookies.get('CloudFront-Policy').replace('_', '=')))
        url = params['Statement'][0]['Resource'][:-1] + self.username + '.m3u8'

        return self.getWantedResolutionPlaylist(url)

    def getStatus(self):
        r = requests.get('https://roompool.live.manyvids.com/roompool/' + self.username + '?private=false', headers=self.headers)
        if r.status_code != 200:
            return Status.UNKNOWN

        self.lastInfo = r.json()

        if self.lastInfo['roomLocationReason'] == "ROOM_VALIDATION_FAILED":
            return Status.NOTEXIST
        if self.lastInfo['roomLocationReason'] == "ROOM_OK":
            r = self.requestStreamInfo()
            if 'withCredentials' not in r.json():
                return Status.OFFLINE
            return Status.PUBLIC

        return Status.UNKNOWN
