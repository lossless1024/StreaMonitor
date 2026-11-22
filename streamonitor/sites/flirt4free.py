import json

import requests
from streamonitor.bot import RoomIdBot
from streamonitor.enums import Status


# Site of Hungarian group AdultPerformerNetwork
class Flirt4Free(RoomIdBot):
    site = 'Flirt4Free'
    siteslug = 'F4F'
    models = {}

    def getWebsiteURL(self):
        return "https://www.flirt4free.com/?model=" + self.username

    def getRoomIdFromUsername(self, username):
        if username not in Flirt4Free.models:
            r = self.session.get(f'https://www.flirt4free.com/?model={username}')

            start = b'window.__homePageData__ = '

            if r.content.find(start) == -1:
                return Status.OFFLINE

            j = r.content[r.content.find(start) + len(start):]
            j = j[j.find(b'['):j.find(b'],\n') + 1]
            j = j[j.find(b'['):j.rfind(b',')] + b']'

            try:
                m = json.loads(j)
            except Exception as e:
                self.log(f'Failed to parse JSON: {e}')
                m = []

            Flirt4Free.models = {
                v['model_seo_name']: v
                for v in m
            }

        if username in Flirt4Free.models:
            return Flirt4Free.models[username]['model_id']
        return None

    def getVideoUrl(self):
        return self.getWantedResolutionPlaylist("https:" + self.lastInfo['data']['hls'][0]['url'])

    def getStatus(self):
        r = self.session.get(f'https://www.flirt4free.com/ws/chat/get-stream-urls.php?model_id={self.room_id}').json()
        self.lastInfo = r
        if r['code'] == 44:
            return Status.NOTEXIST
        if r['code'] == 0:
            s = self.session.get(f'https://www.flirt4free.com/ws/rooms/chat-room-interface.php?a=login_room&model_id={self.room_id}').json()
            if 'config' not in s:
                return Status.UNKNOWN
            status = s['config'].get('room', {}).get('status')
            if status == 'O':
                return Status.PUBLIC
            if status == 'P':
                return Status.PRIVATE
            if status == 'F':
                return Status.OFFLINE

        return Status.UNKNOWN
