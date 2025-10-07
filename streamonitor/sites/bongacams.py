import requests
from streamonitor.bot import Bot
from streamonitor.enums import Status


class BongaCams(Bot):
    site = 'BongaCams'
    siteslug = 'BC'

    def getWebsiteURL(self):
        return "https://bongacams.com/" + self.username
    
    def getPlaylistUrl(self):
        return "https:" + self.lastInfo['localData']['videoServerUrl'] + "/hls/stream_" + self.username + "/playlist.m3u8"

    def getVideoUrl(self):
        return self.getWantedResolutionPlaylist(self.getPlaylistUrl())

    def getStatus(self):
        headers = self.headers | {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Referer': 'https://de.bongacams.net/' + self.username,
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'X-Requested-With': 'XMLHttpRequest'
        }
        data = 'method=getRoomData&args%5B%5D=' + self.username + '&args%5B%5D=false'
        r = requests.post('https://de.bongacams.net/tools/amf.php', data=data, headers=headers)

        if r.status_code == 200:
            self.lastInfo = r.json()
            if self.lastInfo["status"] == "error":
                return Status.NOTEXIST
            if self.username != self.lastInfo['performerData']['username']:
                self.username = self.lastInfo['performerData']['username']
                self.logger = self.getLogger()
            if self.lastInfo['performerData']['showType'] in ['private', 'group']:
                return Status.PRIVATE
            if 'videoServerUrl' in self.lastInfo['localData']:
                r = requests.get(self.getPlaylistUrl())
                if len(r.text) == 25 or r.status_code == 404:
                    return Status.OFFLINE
                return Status.PUBLIC
            else:
                return Status.OFFLINE
        return Status.UNKNOWN
