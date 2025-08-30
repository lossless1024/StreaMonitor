import datetime
import json
import os
from json import JSONDecodeError

import requests
from websocket import WebSocketApp

from streamonitor.bot import Bot
from streamonitor.downloaders.hls import getVideoNativeHLS
from streamonitor.bot_chat import ChatCollectingMixin
from streamonitor.enums import Status


class StripChat(ChatCollectingMixin, Bot):
    site = 'StripChat'
    siteslug = 'SC'

    _initial_data = {}

    def __init__(self, username):
        if StripChat._initial_data == {}:
            self.getInitialData()
        super().__init__(username)
        self.vr = False
        self.url = self.getWebsiteURL()
        self.getVideo = lambda _, url, filename: getVideoNativeHLS(self, url, filename, StripChat.m3u_decoder)
        self.psch = None
        self.pkey = None
        self._model_id = None
        self._chat_websocket = None

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

        if self._model_id is None:
            self._model_id = self.lastInfo["model"]['id']

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


    def prepareChatLog(self, message_callback):
        if 'client' not in StripChat._initial_data or not 'websocket' in StripChat._initial_data['client']:
            self.log("No initial data")
            return

        _ws_initial = StripChat._initial_data['client']['websocket']

        if not self._model_id:
            self.getStatus()
        if not self._model_id:
            return
        model_id = str(self._model_id)

        def on_open(ws):
            ws.send('{"connect":{"token":"' + _ws_initial['token'] + '","name":"js"},"id":1}')
            ws.send('{"subscribe":{"channel":"newChatMessage@' + model_id + '"},"id":2}')
            self.log('Chat logger connected')

            try:
                req = requests.get(
                    f"https://hu.stripchat.com/api/front/v2/models/username/{self.username}/chat?source=regular",
                    headers=self.headers
                )
                if req.status_code != 200:
                    return
                prev_data = req.json()
                if 'messages' in prev_data:
                    previous_chat_messages = req.json()['messages']
                    for message in previous_chat_messages:
                        if message['type'] != 'text':
                            continue
                        timestamp = datetime.datetime.strptime(message['createdAt'], "%Y-%m-%dT%H:%M:%SZ").timestamp()
                        username = message['userData']['username']
                        text = message['details']['body']
                        try:
                            message_callback(username, text, timestamp=timestamp, initial=True)
                        except Exception as e:
                            self.log(f"Error processing message callback: {e}")
                    self.debug('Loaded previous messages')
            except Exception as e:
                self.log(f"Failed to load previous messages: {e}")

        def on_message(conn, t):
            if t == '{}':  # ping
                conn.send('{}')
                self.debug('pingpong')

            elif 'newChatMessage@' in t:  # message
                tss = t.split('\n')
                for ts in tss:
                    try:
                        tj = json.loads(ts)
                    except json.JSONDecodeError:
                        self.log(f"Failed to decode JSON message: {message}")
                        return

                    if 'push' in tj:
                        if tj['push']['channel'] == 'newChatMessage@' + model_id:
                            message = tj['push']['pub']['data']['message']
                            username = message['userData']['username']
                            if message['type'] == 'text':
                                text = message['details']['body']
                                self.debug(f"{datetime.datetime.now().timestamp()!s} - {username}: {text}")
                                try:
                                    message_callback(username, text)
                                except Exception as e:
                                    self.log(f"Error processing message callback: {e}")

        def on_close(conn, arg1, arg2):
            self.log('Chat logger disconnected')

        self._chat_websocket = WebSocketApp(
            _ws_initial['url'], on_open=on_open, on_message=on_message, on_close=on_close)

    def startChatLog(self):
        self._chat_websocket.run_forever()

    def stopChatLog(self):
        self._chat_websocket.close()


Bot.loaded_sites.add(StripChat)
