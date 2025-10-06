from streamonitor.bot import Bot, RoomIdMixin
from streamonitor.enums import Status


class FanslyLive(RoomIdMixin, Bot):
    site = 'FanslyLive'
    siteslug = 'FL'

    def getWebsiteURL(self):
        return "https://fansly.com/live/" + self.username

    def getVideoUrl(self):
        return self.getWantedResolutionPlaylist(self.lastInfo['stream']['playbackUrl'])

    def getRoomId(self):
        r = self.session.get(f'https://apiv3.fansly.com/api/v1/account?usernames={self.username}&ngsw-bypass=true')
        data = r.json()
        for streamer in data.get('response', []):
            if streamer.get('username').lower() == self.username.lower():
                self.username = streamer['username']
                return streamer.get('id')
        return None

    def getStatus(self):
        if self.room_id is None:
            self.room_id = self.getRoomId()
        if self.room_id is None:
            return Status.NOTEXIST

        r = self.session.get(f'https://apiv3.fansly.com/api/v1/streaming/channel/{self.room_id}?ngsw-bypass=true')
        data = r.json()
        if data.get('success') is not True:
            return Status.UNKNOWN

        self.lastInfo = r.json().get('response')

        if not self.lastInfo:
            return Status.NOTEXIST
        if not self.lastInfo.get('stream'):
            return Status.UNKNOWN

        stream = self.lastInfo['stream']
        if stream.get('status') == 2:
            if stream.get('access') is True and 'playbackUrl' in stream:
                return Status.PUBLIC
            else:
                return Status.PRIVATE
        return Status.UNKNOWN


Bot.loaded_sites.add(FanslyLive)
