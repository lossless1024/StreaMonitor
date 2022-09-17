import requests
from streamonitor.bot import Bot


class BongaCams(Bot):
    site = 'BongaCams'
    siteslug = 'BC'

    def getVideoUrl(self):
        return "https:" + \
               self.lastInfo['localData']['videoServerUrl'] + "/hls/stream_" + self.username + "/playlist.m3u8" \
               or None

    def getStatus(self):
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Referer': 'https://de.bongacams.com/' + self.username,
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'X-Requested-With': 'XMLHttpRequest'
        }
        data = 'method=getRoomData&args%5B%5D=' + self.username + '&args%5B%5D=false'
        r = requests.post('https://de.bongacams.com/tools/amf.php', data=data, headers=headers)

        if r.status_code == 200:
            self.lastInfo = r.json()
            if self.lastInfo["status"] == "error":
                return Bot.Status.NOTEXIST
            if 'videoServerUrl' in self.lastInfo['localData']:
                r = requests.get(self.getVideoUrl())
                if len(r.text) == 25 or r.status_code == 404:
                    return Bot.Status.OFFLINE
                return Bot.Status.PUBLIC
            else:
                return Bot.Status.OFFLINE
        return Bot.Status.UNKNOWN


Bot.loaded_sites.add(BongaCams)
