import requests
import bot


class BongaCams(bot.Bot):
    site = 'BongaCams'
    siteslug = 'BC'

    def __init__(self, username):
        super().__init__(username)
        self.lastInfo = None

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
                return bot.Bot.Status.NOTEXIST
            r = requests.get(self.getVideoUrl())
            if len(r.text) == 25:
                return bot.Bot.Status.OFFLINE
            return bot.Bot.Status.PUBLIC
        return bot.Bot.Status.UNKNOWN
