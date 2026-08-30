import itertools
import json
import os.path
import random
import requests
import base64
import hashlib

from streamonitor.bot import RoomIdBot
from streamonitor.downloaders.hls import getVideoNativeHLS
from streamonitor.enums import Status, Gender, COUNTRIES


class StripChat(RoomIdBot):
    site = 'StripChat'
    siteslug = 'SC'

    bulk_update = True
    _mouflon_cache_filename = 'stripchat_mouflon_keys.json'
    _mouflon_keys: dict = None
    _cached_keys: dict[str, bytes] = None
    _remote_keys_attempted = False
    _KEYS_REMOTE_URL = 'https://raw.githubusercontent.com/kesamom/stripchat_mouflon/main/stripchat_mouflon_keys.json'
    _PRIVATE_STATUSES = frozenset(["private", "groupShow", "p2p", "virtualPrivate", "p2pVoice"])
    _OFFLINE_STATUSES = frozenset(["off", "idle"])

    _GENDER_MAP = {
        'female': Gender.FEMALE,
        'male': Gender.MALE,
        'maleFemale': Gender.BOTH,
        'transgenderFemale': Gender.TRANS_WOMAN,
        'transgenderMale': Gender.TRANS_MAN,
        'transsexual': Gender.TRANS,
        'transgender': Gender.TRANS
    }

    if os.path.exists(_mouflon_cache_filename):
        with open(_mouflon_cache_filename) as f:
            try:
                if not isinstance(_mouflon_keys, dict):
                    _mouflon_keys = {}
                _mouflon_keys.update(json.load(f))
                print('Loaded StripChat mouflon key cache')
            except Exception as e:
                print('Error loading mouflon key cache:', e)

    def __init__(self, username, room_id=None):
        super().__init__(username, room_id)
        self.vr = False
        self.getVideo = lambda _, url, filename: getVideoNativeHLS(self, url, filename, StripChat.m3u_decoder)

    @classmethod
    def m3u_decoder(cls, content):
        _mouflon_filename = 'media.mp4'

        def _decode(encrypted_b64: str, key: str) -> str:
            if cls._cached_keys is None:
                cls._cached_keys = {}
            hash_bytes = cls._cached_keys[key] if key in cls._cached_keys \
                else cls._cached_keys.setdefault(key, hashlib.sha256(key.encode("utf-8")).digest())
            encrypted_data = base64.b64decode(encrypted_b64 + "==")
            return bytes(a ^ b for (a, b) in zip(encrypted_data, itertools.cycle(hash_bytes))).decode("utf-8")

        psch, pkey, pdkey = StripChat._getMouflonFromM3U(content)

        if psch == 'v1':
            _mouflon_file_attr = "#EXT-X-MOUFLON:FILE:"
        elif psch == 'v2':
            _mouflon_file_attr = "#EXT-X-MOUFLON:URI:"
        else:
            return None

        decoded = ''
        lines = content.splitlines()
        last_decoded_file = None
        for line in lines:
            if line.startswith(_mouflon_file_attr):
                if psch == 'v1':
                    last_decoded_file = _decode(line[len(_mouflon_file_attr):], pdkey)
                elif psch == 'v2':
                    uri = line[len(_mouflon_file_attr):]
                    encoded_part = uri.split('_')[-2]
                    decoded_part = _decode(encoded_part[::-1], pdkey)
                    last_decoded_file = uri.replace(encoded_part, decoded_part).split('/', maxsplit=4)[4]
            elif line.endswith(_mouflon_filename) and last_decoded_file:
                decoded += (line.replace(_mouflon_filename, last_decoded_file)) + '\n'
                last_decoded_file = None
            else:
                decoded += line + '\n'
        return decoded

    @classmethod
    def getMouflonDecKey(cls, pkey):
        if cls._mouflon_keys is None:
            cls._mouflon_keys = {}
        if pkey in cls._mouflon_keys:
            return cls._mouflon_keys[pkey]
        # Unknown key: try to refresh the key set from the community-maintained list once
        if not cls._remote_keys_attempted:
            cls._remote_keys_attempted = True
            try:
                r = requests.get(cls._KEYS_REMOTE_URL, timeout=10)
                if r.status_code == 200:
                    remote_keys = r.json()
                    if isinstance(remote_keys := remote_keys, dict) and remote_keys:
                        cls._mouflon_keys.update(remote_keys)
                        with open(cls._mouflon_cache_filename, 'w') as f:
                            json.dump(cls._mouflon_keys, f, indent=2)
                        print('Updated StripChat mouflon keys from remote repository')
            except Exception as e:
                print('Failed to update mouflon keys remotely:', e)
        if pkey in cls._mouflon_keys:
            return cls._mouflon_keys[pkey]
        return None

    @staticmethod
    def _getMouflonFromM3U(m3u8_doc):
        _start = 0
        _needle = '#EXT-X-MOUFLON:'
        while _needle in (_doc := m3u8_doc[_start:]):
            _mouflon_start = _doc.find(_needle)
            if _mouflon_start > 0:
                _mouflon = _doc[_mouflon_start:m3u8_doc.find('\n', _mouflon_start)].strip().split(':')
                if len(_mouflon) < 4:
                    _start += _mouflon_start + len(_needle)
                    continue
                psch = _mouflon[2]
                pkey = _mouflon[3]
                pdkey = StripChat.getMouflonDecKey(pkey)
                if pdkey:
                    return psch, pkey, pdkey
            _start += _mouflon_start + len(_needle)
        return None, None, None

    def getWebsiteURL(self):
        return "https://stripchat.com/" + self.username

    def getVideoUrl(self):
        return self.getWantedResolutionPlaylist(None)

    def getPlaylistVariants(self, url):
        url = "https://edge-hls.{host}/hls/{id}{vr}/master/{id}{vr}{auto}.m3u8".format(
                host='doppiocdn.' + random.choice(['org', 'com', 'net', 'media']),
                id=self.room_id,
                vr='_vr' if self.vr else '',
                auto='_auto' if not self.vr else ''
            )
        result = self.session.get(url, headers=self.headers, cookies=self.cookies)
        if result.status_code != 200:
            self.log(f'Failed to get master playlist (HTTP {result.status_code})')
            return []
        m3u_data = result.content.decode("utf-8")
        psch, pkey, pdkey = StripChat._getMouflonFromM3U(m3u_data)
        if pdkey is None:
            self.log(f'Failed to get mouflon decryption key')
            return []
        variants = super().getPlaylistVariants(m3u_data=m3u_data)
        return [variant | {'url': f'{variant["url"]}{"&" if "?" in variant["url"] else "?"}psch={psch}&pkey={pkey}'}
                for variant in variants]

    @staticmethod
    def uniq(length=16):
        chars = ''.join(chr(i) for i in range(ord('a'), ord('z')+1))
        chars += ''.join(chr(i) for i in range(ord('0'), ord('9')+1))
        return ''.join(random.choice(chars) for _ in range(length))

    @classmethod
    def _fetchModelsList(cls, model_ids):
        # The old per-username /cam endpoint is gone (HTTP 418);
        # the bulk list endpoint still works without any special headers.
        base_url = 'https://stripchat.com/api/front/models/list?'
        data_map = {}
        batch_num = 100
        id_list = [str(model_id) for model_id in model_ids]
        for _batch_ids in [id_list for id_list in [id_list[i:i+batch_num] for i in range(0, len(id_list), batch_num)]]:
            session = requests.Session()
            session.headers.update(cls.headers)
            r = session.get(base_url + '&'.join(f'modelIds[]={model_id}' for model_id in _batch_ids), timeout=10)
            try:
                data = r.json()
            except (requests.exceptions.JSONDecodeError, ValueError):
                print('Failed to parse JSON response from models/list')
                return {}
            data_map |= {str(model['id']): model for model in data.get('models', [])}
        return data_map

    def getRoomIdFromUsername(self, username):
        if username == self.username and self.room_id is not None:
            return self.room_id

        r = self.session.get(f'https://hu.stripchat.com/api/front/users/user-ids/{username}', headers=self.headers)
        try:
            data = r.json()
            _id = str(data['id']) if data.get('id') else None
        except requests.exceptions.JSONDecodeError:
            self.log('Failed to parse JSON response')
            return None
        except (KeyError, TypeError):
            self.log('No user ID found')
            return None
        return _id

    def _applyModelData(self, model_data):
        self.lastInfo = {'model': model_data}
        if model_data.get('gender'):
            self.gender = StripChat._GENDER_MAP.get(model_data.get('gender'))
        if model_data.get('country'):
            self.country = model_data.get('country', '').upper()
        elif model_data.get('languages'):
            for lang in model_data['languages']:
                if lang.upper() in COUNTRIES:
                    self.country = lang.upper()
                    break

        status = model_data.get('status')
        if status == "public" and (model_data.get('isOnline') or model_data.get('isLive')):
            return Status.PUBLIC
        if status in self._PRIVATE_STATUSES:
            return Status.PRIVATE
        if status in self._OFFLINE_STATUSES:
            return Status.OFFLINE
        self.logger.warn(f'Got unknown status: {status}')
        return Status.UNKNOWN

    def getStatus(self):
        if not self.room_id:
            # Room ID might have never been resolved or the model was renamed
            self.room_id = self.getRoomIdFromUsername(self.username)
            if not self.room_id:
                return Status.NOTEXIST

        data_map = StripChat._fetchModelsList([self.room_id])
        model_data = data_map.get(str(self.room_id))
        if not model_data:
            return Status.NOTEXIST

        # Models keep their ID when they change their username
        model_username = model_data.get('username')
        if model_data.get('previousUsername') == self.username and model_data.get('username') != self.username:
            self.logger.info(f'Model name changed, new name: {model_data["username"]}')
            _old_dl_dir = self.outputFolder
            self.setUsername(model_data['username'])
            _new_dl_dir = self.outputFolder
            if os.path.exists(_old_dl_dir) and not os.path.exists(_new_dl_dir):
                os.rename(_old_dl_dir, _new_dl_dir)

        return self._applyModelData(model_data)

    @classmethod
    def getStatusBulk(cls, streamers):
        model_ids = {}
        for streamer in streamers:
            if not isinstance(streamer, StripChat):
                continue
            if streamer.room_id:
                model_ids[streamer.room_id] = streamer

        data_map = cls._fetchModelsList(model_ids.keys()) if model_ids else {}

        for model_id, streamer in model_ids.items():
            model_data = data_map.get(str(model_id))
            if not model_data:
                continue  # Don't touch status on transient failures; a missing model may be a glitch
            streamer.gender = cls._GENDER_MAP.get(model_data.get('gender'))
            if model_data.get('country'):
                streamer.country = model_data.get('country', '').upper()
            status = model_data.get('status')
            if status == "public" and (model_data.get("isOnline") or model_data.get("isLive")):
                streamer.setStatus(Status.PUBLIC)
            elif status in cls._PRIVATE_STATUSES:
                streamer.setStatus(Status.PRIVATE)
            elif status in cls._OFFLINE_STATUSES:
                streamer.setStatus(Status.OFFLINE)
            else:
                print(f'[{streamer.siteslug}] {streamer.username}: Bulk update got unknown status: {status}')
                streamer.setStatus(Status.UNKNOWN)
