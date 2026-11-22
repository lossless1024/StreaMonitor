from streamonitor.bot import RoomIdBot
from streamonitor.enums import Status


class FanslyLive(RoomIdBot):
    site = 'FanslyLive'
    siteslug = 'FL'

    def getWebsiteURL(self):
        return "https://fansly.com/live/" + self.username

    def getVideoUrl(self):
        return self.getWantedResolutionPlaylist(self.lastInfo['stream']['playbackUrl'])

    def getUsernameFromRoomId(self, room_id):
        r = self.session.get(f'https://apiv3.fansly.com/api/v1/account?ids={room_id}&ngsw-bypass=true')
        data = r.json()
        for streamer in data.get('response', []):
            if streamer.get('id') == room_id:
                self.username = streamer['username']
                return streamer.get('username')
        return None

    def getRoomIdFromUsername(self, username):
        r = self.session.get(f'https://apiv3.fansly.com/api/v1/account?usernames={username}&ngsw-bypass=true')
        data = r.json()
        for streamer in data.get('response', []):
            if streamer.get('username').lower() == username.lower():
                self.username = streamer['username']
                return streamer.get('id')
        return None

    def getStatus(self):
        if self.room_id is None:
            self.room_id = self.getRoomIdFromUsername(self.username)
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
