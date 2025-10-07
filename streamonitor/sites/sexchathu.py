import time
import requests
from streamonitor.bot import RoomIdBot
from streamonitor.enums import Status


# Site of Hungarian group AdultPerformerNetwork
class SexChatHU(RoomIdBot):
    site = 'SexChatHU'
    siteslug = 'SCHU'

    _performers_list_cache = None
    _performers_list_cache_timestamp = 0

    def _getBabesList(self):
        if SexChatHU._performers_list_cache_timestamp < time.time() - 60 * 60 or \
                SexChatHU._performers_list_cache is None:  # Cache for 1 hour
            req = requests.get('https://sexchat.hu/ajax/api/roomList/babes', headers=self.headers)
            SexChatHU._performers_list_cache = req.json()
            SexChatHU._performers_list_cache_timestamp = time.time()
        return SexChatHU._performers_list_cache

    def getUsernameFromRoomId(self, room_id):
        for performer in self._getBabesList():
            if str(performer['perfid']) == room_id:
                username = performer['screenname']
                return username
        return None

    def getRoomIdFromUsername(self, username):
        for performer in self._getBabesList():
            if performer['screenname'] == username:
                room_id = str(performer['perfid'])
                return room_id
        return None

    def getWebsiteURL(self):
        if self.room_id is None:
            return super().getWebsiteURL()
        return "https://sexchat.hu/mypage/" + self.room_id + "/" + self.username + "/chat"

    def getVideoUrl(self):
        return self.getWantedResolutionPlaylist("https:" + self.lastInfo['onlineParams']['modeSpecific']['main']['hls']['address'])

    def getStatus(self):
        if self.room_id is None:
            return Status.NOTEXIST

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
