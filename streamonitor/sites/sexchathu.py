import requests
from streamonitor.bot import Bot


# Site of Hungarian group AdultPerformerNetwork
class SexChatHU(Bot):
    site = 'SexChatHU'
    siteslug = 'SCHU'

    def __init__(self, room_id):
        self.room_id = room_id
        self.lastInfo = {}
        self.getStatus()
        username = self.lastInfo.get('screenName')
        super().__init__(username)

    def export(self):
        data = super().export()
        data['room_id'] = self.room_id
        return data

    def getVideoUrl(self):
        return "https:" + self.lastInfo['onlineParams']['modeSpecific']['main']['hls']['address']

    def getStatus(self):
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:75.0) Gecko/20100101 Firefox/75.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
        }

        r = requests.get('https://chat.a.apn2.com/chat-api/index.php/room/getRoom?tokenID=guest&roomID=' + self.room_id, headers=headers)
        if r.status_code != 200:
            return Bot.Status.UNKNOWN

        self.lastInfo = r.json()

        if not self.lastInfo["active"]:
            return Bot.Status.NOTEXIST
        elif self.lastInfo["onlineStatus"] == "free":
            return Bot.Status.PUBLIC
        elif self.lastInfo["onlineStatus"] in ['vip', 'group', 'priv']:
            return Bot.Status.PRIVATE
        elif self.lastInfo["onlineStatus"] == "offline":
            return Bot.Status.OFFLINE
        return Bot.Status.UNKNOWN


Bot.loaded_sites.add(SexChatHU)
