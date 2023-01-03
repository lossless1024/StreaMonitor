import json

import requests
from streamonitor.bot import Bot


# Site of Hungarian group AdultPerformerNetwork
class Flirt4Free(Bot):
    site = 'Flirt4Free'
    siteslug = 'F4F'
    models = {}

    def __init__(self, username, room_id=None):
        self.room_id = room_id if room_id else self.getRoomId(username)
        super().__init__(username)

    def getRoomId(self, username):
        if username in Flirt4Free.models:
            return Flirt4Free.models[username]['model_id']

        r = requests.get(f'https://www.flirt4free.com/?model={username}')

        start = b'window.__homePageData__ = '

        if r.content.find(start) == -1:
            return Bot.Status.OFFLINE

        j = r.content[r.content.find(start) + len(start):]
        j = j[j.find(b'['):j.find(b'],\n') + 1]
        j = j[j.find(b'['):j.rfind(b',')] + b']'

        try:
            m = json.loads(j)
            Flirt4Free.models = {v['model_seo_name']: v for v in m}
        except:
            self.log('Failed to parse JSON')
            return None

        if username in Flirt4Free.models:
            return Flirt4Free.models[username]['model_id']
        return None

    def export(self):
        data = super().export()
        data['room_id'] = self.room_id
        return data

    def getVideoUrl(self):
        return self.getWantedResolutionPlaylist("https:" + self.lastInfo['data']['hls'][0]['url'])

    def getStatus(self):
        r = requests.get(f'https://www.flirt4free.com/ws/chat/get-stream-urls.php?model_id={self.room_id}').json()
        self.lastInfo = r
        if r['code'] == 44:
            return Bot.Status.NOTEXIST
        if r['code'] == 0:
            s = requests.get(f'https://www.flirt4free.com/ws/rooms/chat-room-interface.php?a=login_room&model_id={self.room_id}').json()
            if 'config' not in s:
                return Bot.Status.UNKNOWN
            if s['config']['room']['status'] == 'O':
                return Bot.Status.PUBLIC
            if s['config']['room']['status'] == 'P':
                return Bot.Status.PRIVATE
            if s['config']['room']['status'] == 'F':
                return Bot.Status.OFFLINE

        return Bot.Status.UNKNOWN


Bot.loaded_sites.add(Flirt4Free)
