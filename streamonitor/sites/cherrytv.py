import requests
from streamonitor.bot import Bot
from streamonitor.enums import Status


class CherryTV(Bot):
    site = 'Cherry.tv'
    siteslug = 'CHTV'

    def getWebsiteURL(self):
        return "https://www.cherry.tv/" + self.username

    def getVideoUrl(self):
        return self.getWantedResolutionPlaylist(self.lastInfo['broadcast']['pullUrl'])

    def getStatus(self):
        operationName = 'findStreamerBySlug'
        variables = '{"slug": "' + self.username + '"}'
        extensions = '{"persistedQuery":{"version":1,"sha256Hash":"1fd980c874484de0b139ef4a67c867200a87f44aa51caf54319e93a4108a7510"}}'

        r = self.session.get(f'https://api.cherry.tv/graphql?operationName={operationName}&variables={variables}&extensions={extensions}', headers=self.headers)
        self.lastInfo = r.json()['data']['streamer']
        
        if not self.lastInfo:
            return Status.NOTEXIST
        if not self.lastInfo['broadcast']:
            return Status.OFFLINE
        if self.lastInfo['broadcast']['showStatus'] == 'Public':
            return Status.PUBLIC
        return Status.UNKNOWN
