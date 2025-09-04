import re
import time
import datetime
import json
import requests
import base64
import hashlib
from websocket import WebSocketApp

from streamonitor.bot import Bot
from streamonitor.downloaders.hls import getVideoNativeHLS
from streamonitor.bot_chat import ChatCollectingMixin
from streamonitor.enums import Status


class StripChat(ChatCollectingMixin, Bot):
    site = 'StripChat'
    siteslug = 'SC'

    _initial_data = {}
    _static_data = None
    _main_js_data = None
    _doppio_js_data = None
    _mouflon_keys: dict = None
    _cached_keys: dict = None

    def __init__(self, username):
        if StripChat._static_data is None:
            StripChat._static_data = {}
            try:
                self.getInitialData()
            except Exception as e:
                StripChat._static_data = None
                raise e
        while StripChat._static_data == {}:
            time.sleep(1)
        super().__init__(username)
        self.vr = False
        self.url = self.getWebsiteURL()
        self.getVideo = lambda _, url, filename: getVideoNativeHLS(self, url, filename, StripChat.m3u_decoder)
        self._model_id = None
        self._chat_websocket = None

    @classmethod
    def getInitialData(cls):
        r = requests.get('https://stripchat.com/api/front/v3/config/initial', headers=cls.headers)
        if r.status_code != 200:
            raise Exception("Failed to fetch initial data from StripChat")
        StripChat._initial_data = r.json().get('initial')

        r = requests.get('https://hu.stripchat.com/api/front/v3/config/static', headers=cls.headers)
        if r.status_code != 200:
            raise Exception("Failed to fetch static data from StripChat")
        StripChat._static_data = r.json().get('static')

        mmp_origin = StripChat._static_data['features']['MMPExternalSourceOrigin']
        mmp_version = StripChat._static_data['featuresV2']['playerModuleExternalLoading']['mmpVersion']
        mmp_base = f"{mmp_origin}/v{mmp_version}"

        r = requests.get(f"{mmp_base}/main.js", headers=cls.headers)
        if r.status_code != 200:
            raise Exception("Failed to fetch main.js from StripChat")
        StripChat._main_js_data = r.content.decode('utf-8')

        doppio_js_name = re.findall('require[(]"./(Doppio.*?[.]js)"[)]', StripChat._main_js_data)[0]

        r = requests.get(f"{mmp_base}/{doppio_js_name}", headers=cls.headers)
        if r.status_code != 200:
            raise Exception("Failed to fetch doppio.js from StripChat")
        StripChat._doppio_js_data = r.content.decode('utf-8')

    @classmethod
    def m3u_decoder(cls, content):
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

        _, pkey = StripChat._getMouflonFromM3U(content)

        decoded = []
        lines = content.splitlines()
        for idx, line in enumerate(lines):
            if line.startswith("#EXT-X-MOUFLON:FILE:"):
                dec = _decode(line[20:], cls.getMouflonDecKey(pkey))
                decoded.append(lines[idx + 1].replace("media.mp4", dec))
            else:
                decoded.append(line)
        return "\n".join(decoded)

    @classmethod
    def getMouflonDecKey(cls, pkey):
        if not cls._mouflon_keys:
            cls._mouflon_keys = {}

        if pkey in cls._mouflon_keys:
            return cls._mouflon_keys[pkey]

        key = re.findall(f'"{pkey}:(.*?)"', cls._doppio_js_data)[0]
        cls._mouflon_keys[pkey] = key
        return key

    @staticmethod
    def _getMouflonFromM3U(m3u8_doc):
        if '#EXT-X-MOUFLON:' in m3u8_doc:
            _mouflon_start = m3u8_doc.find('#EXT-X-MOUFLON:')
            if _mouflon_start > 0:
                _mouflon = m3u8_doc[_mouflon_start:m3u8_doc.find('\n', _mouflon_start)].strip().split(':')
                psch = _mouflon[2]
                pkey = _mouflon[3]
                return psch, pkey
        return None, None

    def getWebsiteURL(self):
        return "https://stripchat.com/" + self.username

    def getVideoUrl(self):
        return self.getWantedResolutionPlaylist(None)

    def getPlaylistVariants(self, url):
        url = "https://edge-hls.{host}/hls/{id}{vr}/master/{id}{vr}{auto}.m3u8".format(
                host='doppiocdn.com',
                id=self.lastInfo["cam"]["streamName"],
                vr='_vr' if self.vr else '',
                auto='_auto' if not self.vr else ''
            )
        result = requests.get(url, headers=self.headers, cookies=self.cookies)
        m3u8_doc = result.content.decode("utf-8")
        psch, pkey = StripChat._getMouflonFromM3U(m3u8_doc)
        variants = super().getPlaylistVariants(m3u_data=m3u8_doc)
        return [variant | {'url': f'{variant["url"]}{"&" if "?" in variant["url"] else "?"}psch={psch}&pkey={pkey}'}
                for variant in variants]

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
