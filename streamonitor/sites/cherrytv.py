import requests
from streamonitor.bot import Bot


class CherryTV(Bot):
    site = 'CherryTV'
    siteslug = 'CHTV'

    def getVideoUrl(self):
        return self.lastInfo['broadcast']['pullUrl']

    def getStatus(self):
        r = requests.get('https://api.cherry.tv/graphql?operationName=findStreamerBySlug&variables={"slug":"' + self.username + '"}&extensions={"persistedQuery":{"version":1,"sha256Hash":"3a7f547209f75ceca3a7850a49fc37f3762859d208222014163647367edacda3"}}')
        self.lastInfo = r.json()['data']['streamer']
        
        if not self.lastInfo:
            return Bot.Status.NOTEXIST
        if not self.lastInfo['broadcast']:
            return Bot.Status.OFFLINE
        if self.lastInfo['broadcast']['showStatus'] == 'Public':
            return Bot.Status.PUBLIC
        return Bot.Status.UNKNOWN


Bot.loaded_sites.add(CherryTV)
