import requests
from streamonitor.bot import Bot


# Site of Hungarian group AdultPerformerNetwork
class SexChatHU(Bot):
    site = 'SexChatHU'
    siteslug = 'SCHU'

    def __init__(self, username, room_id=None):
        if room_id:
            self.room_id = room_id
            self.username = username
        else:
            try:
                int(username)
            except Exception:
                raise 'Use the room number from the URL instead the name'
            self.room_id = username
            self.getStatus()
            username = self.lastInfo.get('screenName')
            self.lastInfo = {}
        super().__init__(username)

    def export(self):
        data = super().export()
        data['room_id'] = self.room_id
        return data

    def getVideoUrl(self):
        return self.getWantedResolutionPlaylist("https:" + self.lastInfo['onlineParams']['modeSpecific']['main']['hls']['address'])

    def getStatus(self):
        r = requests.get('https://chat.a.apn2.com/chat-api/index.php/room/getRoom?tokenID=guest&roomID=' + self.room_id, headers=self.headers)
        if r.status_code != 200:
            return Bot.Status.UNKNOWN

        self.lastInfo = r.json()

        if not self.lastInfo["active"]:
            return Bot.Status.NOTEXIST
        elif self.lastInfo["onlineStatus"] == "free" and 'hls' in self.lastInfo['onlineParams']['modeSpecific']['main']:
            return Bot.Status.PUBLIC
        elif self.lastInfo["onlineStatus"] in ['vip', 'group', 'priv']:
            return Bot.Status.PRIVATE
        elif self.lastInfo["onlineStatus"] == "offline":
            return Bot.Status.OFFLINE
        return Bot.Status.UNKNOWN


Bot.loaded_sites.add(SexChatHU)
