import requests
from streamonitor.bot import Bot
from streamonitor.enums import Status


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
        self.url = self.getWebsiteURL()

    def getWebsiteURL(self):
        return "https://sexchat.hu/mypage/" + self.room_id + "/" + self.username + "/chat"

    def export(self):
        data = super().export()
        data['room_id'] = self.room_id
        return data

    def getVideoUrl(self):
        return self.getWantedResolutionPlaylist("https:" + self.lastInfo['onlineParams']['modeSpecific']['main']['hls']['address'])

    def getStatus(self):
        r = requests.get('https://chat.a.apn2.com/chat-api/index.php/room/getRoom?tokenID=guest&roomID=' + self.room_id, headers=self.headers)
        if r.status_code != 200:
            return Status.UNKNOWN

        self.lastInfo = r.json()

        if not self.lastInfo["active"]:
            return Status.NOTEXIST
        elif self.lastInfo["onlineStatus"] == "free" and 'hls' in self.lastInfo['onlineParams']['modeSpecific']['main']:
            return Status.PUBLIC
        elif self.lastInfo["onlineStatus"] in ['vip', 'group', 'priv']:
            return Status.PRIVATE
        elif self.lastInfo["onlineStatus"] == "offline":
            return Status.OFFLINE
        return Status.UNKNOWN


Bot.loaded_sites.add(SexChatHU)
