import time
import requests
from streamonitor.bot import RoomIdBot
from streamonitor.enums import Status


# Site of Hungarian group AdultPerformerNetwork
class SexChatHU(RoomIdBot):
    site = 'SexChatHU'
    siteslug = 'SCHU'

    bulk_update = True
    _performers_list_cache = None
    _performers_list_cache_timestamp = 0


    @classmethod
    def _getBabesList(cls, force_update=False):
        if SexChatHU._performers_list_cache_timestamp < time.time() - 60 * 60 or \
                SexChatHU._performers_list_cache is None or force_update:  # Cache for 1 hour
            req = requests.get('https://sexchat.hu/ajax/api/roomList/babes', headers=cls.headers)
            SexChatHU._performers_list_cache = req.json()
            SexChatHU._performers_list_cache_timestamp = time.time()

            for model_data in SexChatHU._performers_list_cache:
                model_id = model_data['perfid']
                model_id = str(model_id)
                model_id = model_id[1:] if model_id.startswith('v') else model_id
                model_data['perfid'] = model_id

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

    @classmethod
    def _getStatusFromData(cls, data):
        onlinestatus = data.get("onlinestatus") or data.get("onlineStatus")
        if onlinestatus == "free":
            if 'onlineParams' not in data and 'onlineparams' not in data:
                return Status.UNKNOWN
            onlineparams = data.get("onlineparams") or data.get("onlineParams")
            if 'modeSpecific' not in onlineparams:
                return Status.UNKNOWN
            if 'main' not in onlineparams['modeSpecific']:
                return Status.UNKNOWN
            if 'hls' not in onlineparams['modeSpecific']['main']:
                return Status.UNKNOWN
            return Status.PUBLIC
        elif onlinestatus in ['vip', 'group', 'priv']:
            return Status.PRIVATE
        elif onlinestatus == "offline":
            return Status.OFFLINE
        return Status.UNKNOWN

    def getStatus(self):
        if self.room_id is None:
            return Status.NOTEXIST

        r = self.session.get('https://chat.a.apn2.com/chat-api/index.php/room/getRoom?tokenID=guest&roomID=' + self.room_id, headers=self.headers)
        if r.status_code != 200:
            return Status.UNKNOWN

        self.lastInfo = r.json()
        if not self.lastInfo["active"]:
            return Status.NOTEXIST
        return self._getStatusFromData(self.lastInfo)

    @classmethod
    def getStatusBulk(cls, streamers):
        model_ids = {}
        for streamer in streamers:
            if not isinstance(streamer, SexChatHU):
                continue
            if streamer.room_id:
                model_ids[streamer.room_id] = streamer
        if len(model_ids) == 0:
            return

        babes_list = cls._getBabesList()
        if not babes_list:
            return
        data_map = {model['perfid']: model for model in babes_list}

        for model_id, streamer in model_ids.items():
            model_data = data_map.get(model_id)
            if not model_data:
                streamer.setStatus(Status.UNKNOWN)
                continue
            streamer.lastInfo = model_data
            status = cls._getStatusFromData(model_data)
            if status in [Status.PUBLIC, Status.PRIVATE, Status.OFFLINE]:
                streamer.setStatus(status)
