import requests
from streamonitor.bot import Bot
from streamonitor.enums import Status


class CamsCom(Bot):
    site = 'CamsCom'
    siteslug = 'CC'

    def getWebsiteURL(self):
        return "https://cams.com/" + self.username

    def getVideoUrl(self):
        return f'https://camscdn.cams.com/camscdn/cdn-{self.username.lower()}.m3u8'

    def getStatus(self):
        r = self.session.get(f'https://beta-api.cams.com/models/stream/{self.username}/')
        self.lastInfo = r.json()
        
        if 'stream_name' not in self.lastInfo:
            return Status.NOTEXIST
        if self.lastInfo['online'] == '0':
            return Status.OFFLINE
        if self.lastInfo['online'] == '1':
            return Status.PUBLIC
        if self.lastInfo['online'] is not None:
            return Status.PRIVATE
            
        return Status.UNKNOWN

# Known online flag states:
# 0: Offline
# 1: Public
# 2: Nude show
# 3: Private
# 4: Admin/Exclusive
# 6: Ticket show
# 7: Voyeur
# 10: Party
# 11: Goal up
# 12: Goal down
# 13: Group
# 14: C2C

