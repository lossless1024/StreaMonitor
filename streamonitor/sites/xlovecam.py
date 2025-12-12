import requests
from streamonitor.bot import Bot
from streamonitor.enums import Status


class XLoveCam(Bot):
    site = 'XLoveCam'
    siteslug = 'XLC'

    def __init__(self, username):
        super().__init__(username)
        self._id = self.getPerformerId()

    def getPerformerId(self):
        data = {
            'config[nickname]':	self.username,
            'config[favorite]':	"0",
            'config[recent]': "0",
            'config[vip]': "0",
            'config[sort][id]':	"35",
            'offset[from]':	"0",
            'offset[length]': "35",
            'origin': "filter-chg",
            'stat':	"0",
        }
        r = requests.post(f'https://www.xlovecam.com/hu/performerAction/onlineList', headers=self.headers, data=data)
        if not r.ok:
            return None
        resp = r.json()
        if 'content' not in resp:
            return None
        if 'performerList' not in resp['content']:
            return None
        for performer in resp['content']['performerList']:
            if performer['nickname'].lower() == self.username.lower():
                return performer['id']
        return None

    def getVideoUrl(self):
        return self.lastInfo.get('hlsPlaylistFree')

    def getStatus(self):
        if self._id is None:
            return Status.NOTEXIST

        data = {
            'performerId': self._id,
        }
        r = requests.post(f'https://www.xlovecam.com/hu/performerAction/getPerformerRoom', headers=self.headers, data=data)

        if not r.ok:
            return Status.UNKNOWN
        if 'content' not in r.json():
            return Status.UNKNOWN
        if 'performer' not in r.json()['content']:
            return Status.UNKNOWN
        self.lastInfo = r.json()['content']['performer']

        if not self.lastInfo.get('enabled'):
            return Status.NOTEXIST
        if self.lastInfo.get('online') == 1:
            if 'hlsPlaylistFree' not in self.lastInfo:
                return Status.UNKNOWN
            url = self.lastInfo.get('hlsPlaylistFree')
            r_m3u = self.session.get(url)
            m3u_data = r_m3u.content
            if m3u_data.startswith(b'{') or b'EXTM3U' not in m3u_data:
                return Status.PRIVATE
            return Status.PUBLIC
        if self.lastInfo.get('online') == 0:
            return Status.OFFLINE
        return Status.UNKNOWN
