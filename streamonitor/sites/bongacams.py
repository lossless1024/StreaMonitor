import requests
from streamonitor.bot import Bot


class BongaCams(Bot):
    site = 'BongaCams'
    siteslug = 'BC'

    def getPlaylistUrl(self):
        return "https:" + self.lastInfo['localData']['videoServerUrl'] + "/hls/stream_" + self.username + "/playlist.m3u8"

    def getVideoUrl(self):
        return self.getBestSubPlaylist(self.getPlaylistUrl(), position=-1)

    def getStatus(self):
        headers = {
            'User-Agent': 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:75.0) Gecko/20100101 Firefox/75.0',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Referer': 'https://de.bongacams.net/' + self.username,
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'X-Requested-With': 'XMLHttpRequest'
        }
        data = 'method=getRoomData&args%5B%5D=' + self.username + '&args%5B%5D=false'
        r = requests.post('https://de.bongacams.net/tools/amf.php', data=data, headers=headers)

        if r.status_code == 200:
            self.lastInfo = r.json()
            self.username = self.lastInfo['performerData']['username']
            if self.lastInfo["status"] == "error":
                return Bot.Status.NOTEXIST
            if 'videoServerUrl' in self.lastInfo['localData']:
                r = requests.get(self.getPlaylistUrl())
                if len(r.text) == 25 or r.status_code == 404:
                    return Bot.Status.OFFLINE
                return Bot.Status.PUBLIC
            else:
                return Bot.Status.OFFLINE
        return Bot.Status.UNKNOWN


Bot.loaded_sites.add(BongaCams)
