import time
import requests
import socketio
import engineio.packet

from parameters import DEBUG
from streamonitor.bot import Bot
from streamonitor.bot_chat import ChatCollectingMixin
from streamonitor.enums import Status


# Site of Hungarian group AdultPerformerNetwork
class SexChatHU(ChatCollectingMixin, Bot):
    site = 'SexChatHU'
    siteslug = 'SCHU'

    _performers_list_cache = None
    _performers_list_cache_timestamp = 0

    def __init__(self, username, room_id=None):
        super().__init__(username)
        if room_id:
            self.room_id = room_id
        elif username.isnumeric():
            self.room_id = username
        else:
            if SexChatHU._performers_list_cache_timestamp < time.time() - 60 * 60 or \
                    SexChatHU._performers_list_cache is None:  # Cache for 1 hour
                req = requests.get('https://sexchat.hu/ajax/api/roomList/babes', headers=self.headers)
                SexChatHU._performers_list_cache = req.json()
                SexChatHU._performers_list_cache_timestamp = time.time()
            for performer in SexChatHU._performers_list_cache:
                if performer['screenname'] == username:
                    self.room_id = str(performer['perfid'])
                    self.username = performer['screenname']
                    break
            else:
                super().__init__(username)
                self.sc = Status.NOTEXIST
                return
        self.url = self.getWebsiteURL()
        self._chat_sio = None

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

    def prepareChatLog(self, message_callback):
        self._chat_sio = sio = socketio.Client(logger=DEBUG, engineio_logger=DEBUG)

        def chat_ping():
            ping_timeout = 25
            while sio.connected:
                sio.emit('pingping', {'ping': True})
                for _ in range(ping_timeout):
                    if not sio.connected:
                        return
                    sio.sleep(1)

        def chat_register():
            sio.emit('call', {"method": "joinRoom", "roomid": self.room_id, "dropOldClient": True, "mode": "free"})
            #sio.emit('call', {'method': 'registerRoomStatusCallback'})
            #sio.emit('call', {'method': 'getRoomList'})

        @sio.event
        def connect():
            self.log('Chat logger connected')
            sio.eio._send_packet(engineio.packet.Packet(engineio.packet.PING, 'probe'))
            time.sleep(1)
            sio.eio._send_packet(engineio.packet.Packet(engineio.packet.UPGRADE))
            sio.emit('call', {
                "authenticate": "guest", "userbase": "sexchat", "flashid": -1, "pingTimeout": 30
            }, callback=chat_register)
            sio.start_background_task(chat_ping)

        @sio.event
        def chatMessage(data):
            username = data['from']
            text = data['message']['text']
            message_callback(username, text)
            self.debug(f"{username}: {text}")

        @sio.event
        def disconnect():
            self.log('Chat logger disconnected')

    def startChatLog(self):
        self._chat_sio.connect('https://chatserver.apn2.com')

    def stopChatLog(self):
        self._chat_sio.eio.disconnect()


Bot.loaded_sites.add(SexChatHU)
