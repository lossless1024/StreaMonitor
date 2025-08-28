import requests
from streamonitor.bot import Bot
from streamonitor.downloaders.hls import getVideoNativeHLS
from streamonitor.enums import Status


class StripChat(Bot):
    site = 'StripChat'
    siteslug = 'SC'

    def __init__(self, username):
        super().__init__(username)
        self.vr = False
        self.url = self.getWebsiteURL()
        self.getVideo = lambda _, url, filename: getVideoNativeHLS(self, url, filename, StripChat.m3u_decoder)
        self.psch = None
        self.pkey = None

    def getWebsiteURL(self):
        return "https://stripchat.com/" + self.username

    def getVideoUrl(self):
        return self.getWantedResolutionPlaylist(None)

    def getPlaylistVariants(self, url):
        url = "https://edge-hls.{host}/hls/{id}{vr}/master/{id}{vr}_auto.m3u8".format(
                host='doppiocdn.com',
                id=self.lastInfo["cam"]["streamName"],
                vr='_vr' if self.vr else '',
            )
        result = requests.get(url, headers=self.headers, cookies=self.cookies)
        m3u8_doc = result.content.decode("utf-8")

        if '#EXT-X-MOUFLON' in m3u8_doc:
            _mouflon_start = m3u8_doc.find('#EXT-X-MOUFLON:')
            if _mouflon_start > 0:
                _mouflon = m3u8_doc[_mouflon_start:m3u8_doc.find('\n', _mouflon_start)].strip().split(':')
                self.psch = _mouflon[2]
                self.pkey = _mouflon[3]

        variants = super().getPlaylistVariants(m3u_data=m3u8_doc)
        return [variant | {'url': f'{variant["url"]}?psch={self.psch}&pkey={self.pkey}'} for variant in variants]

    def getStatus(self):
        r = requests.get('https://stripchat.com/api/vr/v2/models/username/' + self.username, headers=self.headers)
        if r.status_code != 200:
            return Status.UNKNOWN

        self.lastInfo = r.json()

        if self.lastInfo["model"]["status"] == "public" and self.lastInfo["isCamAvailable"] and self.lastInfo['cam']["isCamActive"]:
            return Status.PUBLIC
        if self.lastInfo["model"]["status"] in ["private", "groupShow", "p2p", "virtualPrivate", "p2pVoice"]:
            return Status.PRIVATE
        if self.lastInfo["model"]["status"] in ["off", "idle"]:
            return Status.OFFLINE
        self.logger.warn(f'Got unknown status: {self.lastInfo["model"]["status"]}')
        return Status.UNKNOWN

    _cached_keys: dict = None

    @classmethod
    def m3u_decoder(cls, content):
        import base64
        import hashlib

        def _decode(encrypted_b64: str, key: str) -> str:
            if cls._cached_keys is None:
                cls._cached_keys = {}
            if key not in cls._cached_keys:
                cls._cached_keys[key] = hashlib.sha256(key.encode("utf-8")).digest()
            hash_bytes = cls._cached_keys[key]
            hash_len = len(hash_bytes)

            encrypted_data = base64.b64decode(encrypted_b64 + "==")

            decrypted_bytes = bytearray()
            for i, cipher_byte in enumerate(encrypted_data):
                key_byte = hash_bytes[i % hash_len]
                decrypted_byte = cipher_byte ^ key_byte
                decrypted_bytes.append(decrypted_byte)

            plaintext = decrypted_bytes.decode("utf-8")
            return plaintext

        decoded = []
        lines = content.splitlines()
        for idx, line in enumerate(lines):
            if line.startswith("#EXT-X-MOUFLON:FILE:"):
                dec = _decode(line[20:], "".join(
                    [chr(a ^ b) for a, b in
                     zip([48, 17, 22, 7, 15, 80, 16, 7, 8, 95, 6, 28, 43, 7, 67, 0], b"adsfadsfafdsafva")]))
                decoded.append(lines[idx + 1].replace("media.mp4", dec))
            else:
                decoded.append(line)
        return "\n".join(decoded)


Bot.loaded_sites.add(StripChat)
