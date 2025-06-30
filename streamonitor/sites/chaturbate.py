import json
import re
from random import randint
from urllib.parse import urlencode

import requests
from websocket import WebSocketApp

from streamonitor.bot import Bot
from streamonitor.bot_chat import ChatCollectingMixin
from streamonitor.enums import Status


class Chaturbate(ChatCollectingMixin, Bot):
    site = 'Chaturbate'
    siteslug = 'CB'

    def __init__(self, username):
        super().__init__(username)
        self.sleep_on_offline = 30
        self.sleep_on_error = 60
        self.url = self.getWebsiteURL()
        self._chat_websocket = None

    def getWebsiteURL(self):
        return "https://www.chaturbate.com/" + self.username

    def getVideoUrl(self):
        url = self.lastInfo['url']
        if self.lastInfo.get('cmaf_edge'):
            url = url.replace('playlist.m3u8', 'playlist_sfm4s.m3u8')
            url = re.sub('live-.+amlst', 'live-c-fhls/amlst', url)

        return self.getWantedResolutionPlaylist(url)

    def getStatus(self):
        headers = {"X-Requested-With": "XMLHttpRequest"}
        data = {"room_slug": self.username, "bandwidth": "high"}

        try:
            r = requests.post("https://chaturbate.com/get_edge_hls_url_ajax/", headers=headers, data=data)
            self.lastInfo = r.json()

            if self.lastInfo["room_status"] == "public":
                status = Status.PUBLIC
            elif self.lastInfo["room_status"] in ["private", "hidden"]:
                status = Status.PRIVATE
            else:
                status = Status.OFFLINE
        except:
            status = Status.RATELIMIT

        self.ratelimit = status == Status.RATELIMIT
        return status

    def prepareChatLog(self, message_callback):
        req = requests.get('https://chaturbate.com', headers=self.headers)
        if req.status_code != 200:
            self.logger.error(f'Failed to get main page. sc {req.status_code!s}')
            return
        csrf_cookie = req.cookies.get('csrftoken')

        req = requests.get(f'https://chaturbate.com/api/chatvideocontext/{self.username}/')
        if req.status_code != 200:
            self.logger.error(f'Failed to get chat context for {self.username}: {req.text}')
            return
        room_data = req.json()
        broadcaster_uid = room_data.get('broadcaster_uid')
        if not broadcaster_uid:
            self.logger.error(f'Invalid broadcaster uid for {self.username}')
            return

        broadcaster_topics = [
            'RoomAnonPresenceTopic', 'QualityUpdateTopic', 'LatencyUpdateTopic', 'RoomMessageTopic',
            'RoomFanClubJoinedTopic', 'RoomPurchaseTopic', 'RoomNoticeTopic', 'RoomTipAlertTopic', 'RoomShortcodeTopic',
            'RoomPasswordProtectedTopic', 'RoomModeratorPromotedTopic', 'RoomModeratorRevokedTopic', 'RoomStatusTopic',
            'RoomTitleChangeTopic', 'RoomSilenceTopic', 'RoomKickTopic', 'RoomUpdateTopic', 'RoomSettingsTopic',
            'ViewerPromotionTopic', 'RoomEnterLeaveTopic', 'GameUpdateTopic'
        ]

        data = {
            'presence_id': '',
            'topics': json.dumps({
                "GlobalPushServiceBackendChangeTopic#GlobalPushServiceBackendChangeTopic": {},
            } | {
                f"{topic}#{topic}:{broadcaster_uid}": {"broadcaster_uid": broadcaster_uid}
                for topic in broadcaster_topics
            }),
            'backend': 'a',
            'csrfmiddlewaretoken': csrf_cookie
        }
        req = requests.post(
            f'https://chaturbate.com/push_service/auth/',
            data=data,
            cookies={'csrftoken': csrf_cookie},
            headers=self.headers | {"X-Requested-With": "XMLHttpRequest"}
        )
        if req.status_code != 200:
            raise Exception(f"Failed to authenticate with Chat Service: status_code {req.status_code}")
        auth_data = req.json()
        token = auth_data.get('token')

        sock_params = {
            'access_token': token,
            'heartbeats': 'true',
            'v': '2',
            'agent': 'ably-js/1.2.37 browser',
            'remainPresentFor': '0',
        }
        req = requests.get(
            'https://realtime.pa.highwebmedia.com/comet/connect',
            params=sock_params | {
                'stream': 'false',
                'rnd': randint(10000000000000000, 90000000000000000)
            },
            headers=self.headers | {"X-Requested-With": "XMLHttpRequest"}
        )
        connect_data = req.json()

        def on_open(ws):
            ws.send('{"action":18}')
            ws.send('{"action":10,"channel":"global:push_service","params":{},"flags":327680}')
            ws.send('{"action":10,"channel":"room:grouped:' + broadcaster_uid + ':0","params":{},"flags":327680}')
            self.log('Chat logger connected')

        def on_message(conn, t):
            self.debug(t)
            t = json.loads(t)
            if 'channel' not in t:
                return
            if t['channel'] != f'room:grouped:{broadcaster_uid}:0':
                return
            if 'messages' in t:
                for message in t['messages']:
                    if message['encoding'] != 'json':
                        continue
                    message_data = json.loads(message['data'])
                    if message_data['_topic'] == 'RoomMessageTopic':
                        timestamp = message_data['ts']
                        username = message_data['from_user']['username']
                        text = message_data['message']
                        text = ' '.join(text.split('%%%')[::2]).strip()
                        if text == '':
                            continue
                        try:
                            message_callback(username, text, timestamp=timestamp)
                        except Exception as e:
                            self.log(f"Error processing message callback: {e}")

        def on_close(conn, arg1, arg2):
            self.log('Chat logger disconnected')

        ws_params = {
            'format': 'json',
            'upgrade': connect_data[0]['connectionDetails']['connectionKey']
        }
        ws_url = f"wss://{auth_data['settings']['realtime_host']}?" + urlencode(sock_params | ws_params)
        self._chat_websocket = WebSocketApp(ws_url, on_open=on_open, on_message=on_message, on_close=on_close)

    def startChatLog(self):
        if self._chat_websocket:
            self._chat_websocket.run_forever()
        else:
            self.log("Websocket connection not established.")

    def stopChatLog(self):
        if self._chat_websocket:
            self._chat_websocket.close()


Bot.loaded_sites.add(Chaturbate)
