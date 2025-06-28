import datetime
import json
import os
from json import JSONDecodeError

import requests
from websocket import WebSocketApp

from streamonitor.bot import Bot
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
        self._model_id = None
        self._chat_websocket = None

    def getWebsiteURL(self):
        return "https://stripchat.com/" + self.username

    def getVideoUrl(self):
        return self.getWantedResolutionPlaylist(None)

    def getPlaylistVariants(self, url):
        def formatUrl(master, auto):
            return "https://edge-hls.{host}/hls/{id}{vr}/{master}/{id}{vr}{auto}.m3u8".format(
            host='doppiocdn.com',
            id=self.lastInfo["cam"]["streamName"],
            master='master' if master else '',
            auto='_auto' if auto else '',
            vr='_vr' if self.vr else '')

        variants = []
        variants.extend(super().getPlaylistVariants(formatUrl(True, False)))
        variants.extend(super().getPlaylistVariants(formatUrl(True, True)))
        variants.extend(super().getPlaylistVariants(formatUrl(False, True)))
        variants.extend(super().getPlaylistVariants(formatUrl(False, False)))
        return variants

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

    def getInitialData(self):
        r = requests.get('https://stripchat.com/api/front/v3/config/initial', headers=self.headers)
        if r.status_code != 200:
            raise Exception("Failed to fetch initial data from StripChat")
        StripChat._initial_data = r.json().get('initial')

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
