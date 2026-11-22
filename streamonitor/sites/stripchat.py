import itertools
import json
import os.path
import random
import requests
import base64
import hashlib
import re
import threading
import time

from streamonitor.bot import RoomIdBot
from streamonitor.downloaders.hls import getVideoNativeHLS
from streamonitor.enums import Status, Gender, COUNTRIES


class StripChat(RoomIdBot):
    """StripChat support.

    Mouflon is StripChat's custom HLS playlist obfuscation.  Encrypted media
    lines contain a playlist key identifier; the cached/decrypted key in
    ``stripchat_mouflon_keys.json`` is required to translate them to real
    segment URIs before downloading.
    """
    site = 'StripChat'
    siteslug = 'SC'

    bulk_update = True
    _static_data = None
    _mouflon_cache_filename = os.path.abspath(
        os.path.join(os.path.dirname(__file__), '..', '..', 'stripchat_mouflon_keys.json')
    )
    _mouflon_keys: dict = None
    _cached_keys: dict[str, bytes] = None
    _user_id_cache: dict[str, str] = {}
    _statusSession = None
    _mouflon_refresh_lock = threading.Lock()
    _mouflon_last_refresh = 0
    _mouflon_refresh_thread = None
    _mouflon_remote_keys_url = (
        'https://raw.githubusercontent.com/kesamom/stripchat_mouflon/'
        'main/stripchat_mouflon_keys.json'
    )
    _PRIVATE_STATUSES = frozenset(["private", "groupShow", "p2p", "virtualPrivate", "p2pVoice"])
    _OFFLINE_STATUSES = frozenset(["off", "idle"])

    _GENDER_MAP = {
        'female': Gender.FEMALE,
        'male': Gender.MALE,
        'maleFemale': Gender.BOTH
    }

    if os.path.exists(_mouflon_cache_filename):
        with open(_mouflon_cache_filename) as f:
            try:
                cached_keys = json.load(f)
                if isinstance(cached_keys, dict):
                    _mouflon_keys = cached_keys
                print('Loaded StripChat mouflon key cache')
            except Exception as e:
                print('Error loading mouflon key cache:', e)
    _mouflon_meta_filename = _mouflon_cache_filename + '.meta.json'
    if os.path.exists(_mouflon_meta_filename):
        try:
            with open(_mouflon_meta_filename, 'r', encoding='utf-8') as meta_file:
                _mouflon_last_refresh = float(json.load(meta_file).get('refreshed_at', 0))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            _mouflon_last_refresh = 0

    def __init__(self, username, room_id=None):
        StripChat.scheduleMouflonRefresh(max_age=86400)

        super().__init__(username, room_id)
        self._id = None
        self.vr = False
        self.getVideo = lambda _, url, filename: getVideoNativeHLS(self, url, filename, StripChat.m3u_decoder)

    @classmethod
    def getInitialData(cls):
        session = requests.Session()
        r = session.get('https://stripchat.com/api/front/v3/config/static', headers=cls.headers)
        if r.status_code != 200:
            raise Exception("Failed to fetch static data from StripChat")
        StripChat._static_data = r.json().get('static')

    @classmethod
    def _saveMouflonKeys(cls):
        if cls._mouflon_keys is None:
            cls._mouflon_keys = {}
        temporary = cls._mouflon_cache_filename + '.tmp'
        with open(temporary, 'w', encoding='utf-8') as cache_file:
            json.dump(cls._mouflon_keys, cache_file, sort_keys=True, indent=2)
        os.replace(temporary, cls._mouflon_cache_filename)
        cls._saveMouflonMeta()

    @classmethod
    def _saveMouflonMeta(cls):
        temporary = cls._mouflon_meta_filename + '.tmp'
        with open(temporary, 'w', encoding='utf-8') as meta_file:
            json.dump(
                {'refreshed_at': cls._mouflon_last_refresh},
                meta_file,
                sort_keys=True,
            )
        os.replace(temporary, cls._mouflon_meta_filename)

    @classmethod
    def _extractMouflonKeys(cls, content):
        if not content:
            return {}

        found = {}
        try:
            data = json.loads(content)
            if isinstance(data, dict):
                for pkey, pdkey in data.items():
                    if (
                        isinstance(pkey, str)
                        and isinstance(pdkey, str)
                        and re.fullmatch(r'[A-Za-z0-9_-]{12,}', pkey)
                        and re.fullmatch(r'[A-Za-z0-9_-]{12,}', pdkey)
                    ):
                        found[pkey] = pdkey
            stack = [data]
            while stack:
                value = stack.pop()
                if isinstance(value, dict):
                    pkey = value.get('pkey')
                    pdkey = value.get('pdkey') or value.get('decryptionKey') or value.get('decryption_key')
                    if (
                        isinstance(pkey, str)
                        and isinstance(pdkey, str)
                        and len(pkey) >= 6
                        and len(pdkey) >= 8
                    ):
                        found[pkey] = pdkey
                    stack.extend(value.values())
                elif isinstance(value, list):
                    stack.extend(value)
        except (json.JSONDecodeError, TypeError):
            pass

        lower_content = content.lower()
        if 'mouflon' not in lower_content and 'pkey' not in lower_content:
            return found

        for match in re.finditer(
            r'["\']pkey["\']\s*[:=]\s*["\']([^"\']{6,})["\'][^}]{0,300}'
            r'["\'](?:pdkey|decryption[_-]?key)["\']\s*[:=]\s*["\']([^"\']{8,})["\']',
            content,
            re.IGNORECASE,
        ):
            pkey, decryption_key = match.groups()
            found[pkey] = decryption_key
        return found

    @classmethod
    def refreshMouflonKeys(cls, max_age=300):
        now = time.time()
        if cls._mouflon_last_refresh and now - cls._mouflon_last_refresh < max_age:
            return False

        with cls._mouflon_refresh_lock:
            if cls._mouflon_last_refresh and now - cls._mouflon_last_refresh < max_age:
                return False

            if cls._mouflon_keys is None:
                cls._mouflon_keys = {}

            try:
                discovered = {}
                try:
                    from curl_cffi import requests as curl_requests
                    remote_response = curl_requests.get(
                        cls._mouflon_remote_keys_url,
                        impersonate='chrome',
                        timeout=5,
                    )
                    if remote_response.status_code == 200:
                        discovered.update(
                            cls._extractMouflonKeys(remote_response.text)
                        )
                    response = curl_requests.get(
                        'https://stripchat.com/',
                        impersonate='chrome',
                        timeout=5,
                    )
                except ImportError:
                    remote_response = requests.get(
                        cls._mouflon_remote_keys_url,
                        headers=cls.headers,
                        timeout=5,
                    )
                    if remote_response.status_code == 200:
                        discovered.update(
                            cls._extractMouflonKeys(remote_response.text)
                        )
                    response = requests.get(
                        'https://stripchat.com/',
                        headers=cls.headers,
                        timeout=5,
                    )
                previous_count = len(cls._mouflon_keys)
                cls._mouflon_keys.update(discovered)
                if len(cls._mouflon_keys) != previous_count:
                    cls._mouflon_last_refresh = time.time()
                    cls._saveMouflonKeys()
                    cls._cached_keys = None
                if response.status_code != 200:
                    cls._mouflon_last_refresh = now
                    cls._saveMouflonMeta()
                    return False

                discovered.update(cls._extractMouflonKeys(response.text))
                script_matches = re.findall(
                    r'(?:src|href)=["\']([^"\']+\.js[^"\']*)["\']',
                    response.text,
                )
                checked_scripts = 0
                for script_match in dict.fromkeys(script_matches):
                    if len(discovered) > 100:
                        break
                    if checked_scripts >= 12:
                        break
                    script_url = script_match
                    if script_url.startswith('/'):
                        script_url = 'https://stripchat.com' + script_match
                    if not script_url.startswith('https://'):
                        continue
                    try:
                        script_response = curl_requests.get(
                            script_url,
                            impersonate='chrome',
                            timeout=3,
                        ) if 'curl_requests' in locals() else requests.get(
                            script_url,
                            headers=cls.headers,
                            timeout=3,
                        )
                        checked_scripts += 1
                        if script_response.status_code == 200:
                            discovered.update(
                                cls._extractMouflonKeys(script_response.text)
                            )
                    except Exception:
                        continue

                previous_count = len(cls._mouflon_keys)
                cls._mouflon_keys.update(discovered)
                if len(cls._mouflon_keys) != previous_count:
                    cls._saveMouflonKeys()
                    cls._cached_keys = None
                    print(
                        f"Added {len(cls._mouflon_keys) - previous_count} "
                        "StripChat Mouflon key(s)"
                    )
                cls._mouflon_last_refresh = time.time()
                cls._saveMouflonMeta()
                return len(cls._mouflon_keys) != previous_count
            except Exception as error:
                cls._mouflon_last_refresh = time.time()
                cls._saveMouflonMeta()
                print(f'Could not refresh StripChat Mouflon keys: {error}')
                return False

    @classmethod
    def scheduleMouflonRefresh(cls, max_age=86400):
        now = time.time()
        if cls._mouflon_last_refresh and now - cls._mouflon_last_refresh < max_age:
            return False
        if cls._mouflon_refresh_thread and cls._mouflon_refresh_thread.is_alive():
            return False

        cls._mouflon_refresh_thread = threading.Thread(
            target=cls.refreshMouflonKeys,
            kwargs={'max_age': max_age},
            name='stripchat-mouflon-refresh',
            daemon=True,
        )
        cls._mouflon_refresh_thread.start()
        return True

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

        choices = StripChat._getMouflonChoices(content)
        if not choices:
            return None

        for psch, pkey, pdkey in choices:
            try:
                if psch == 'v1':
                    mouflon_file_attr = "#EXT-X-MOUFLON:FILE:"
                elif psch == 'v2':
                    mouflon_file_attr = "#EXT-X-MOUFLON:URI:"
                else:
                    continue

                decoded = ''
                lines = content.splitlines()
                last_decoded_file = None
                decoded_parts = 0
                for line in lines:
                    if line.startswith(mouflon_file_attr):
                        if psch == 'v1':
                            last_decoded_file = _decode(
                                line[len(mouflon_file_attr):],
                                pdkey,
                            )
                        elif psch == 'v2':
                            uri = line[len(mouflon_file_attr):]
                            encoded_part = uri.split('_')[-2]
                            decoded_part = _decode(encoded_part[::-1], pdkey)
                            last_decoded_file = uri.replace(
                                encoded_part,
                                decoded_part,
                            ).split('/', maxsplit=4)[4]
                    elif line.endswith(_mouflon_filename) and last_decoded_file:
                        decoded += (
                            line.replace(_mouflon_filename, last_decoded_file)
                            + '\n'
                        )
                        last_decoded_file = None
                        decoded_parts += 1
                    else:
                        decoded += line + '\n'
                if decoded_parts > 0:
                    return decoded
            except Exception:
                continue
        return None

    @classmethod
    def getMouflonDecKey(cls, pkey):
        if cls._mouflon_keys is None:
            cls._mouflon_keys = {}
        if pkey in cls._mouflon_keys:
            return cls._mouflon_keys[pkey]
        cls.scheduleMouflonRefresh(max_age=300)
        return None

    @staticmethod
    def _getMouflonFromM3U(m3u8_doc):
        choices = StripChat._getMouflonChoices(m3u8_doc)
        if choices:
            return choices[0]
        for line in m3u8_doc.splitlines():
            if not line.startswith('#EXT-X-MOUFLON:'):
                continue
            fields = line.strip().split(':')
            mouflon_fields = fields[1:]
            for index, field in enumerate(mouflon_fields):
                if field.upper() == 'PSCH' and index + 2 < len(mouflon_fields):
                    return (
                        mouflon_fields[index + 1],
                        mouflon_fields[index + 2],
                        None,
                    )
        return None, None, None

    @staticmethod
    def _getMouflonChoices(m3u8_doc):
        choices = []
        for line in m3u8_doc.splitlines():
            if not line.startswith('#EXT-X-MOUFLON:'):
                continue
            fields = line.strip().split(':')
            if len(fields) < 4:
                continue
            mouflon_fields = fields[1:]
            psch = None
            pkey = None
            for index, field in enumerate(mouflon_fields):
                if field.upper() == 'PSCH' and index + 2 < len(mouflon_fields):
                    psch = mouflon_fields[index + 1]
                    pkey = mouflon_fields[index + 2]
                    break
            if psch is None or pkey is None:
                psch = fields[-2]
                pkey = fields[-1]
            pdkey = StripChat.getMouflonDecKey(pkey)
            if pdkey:
                choice = (psch, pkey, pdkey)
                if choice not in choices:
                    choices.append(choice)
        return choices

    def getWebsiteURL(self):
        return "https://stripchat.com/" + self.username

    def getVideoUrl(self):
        return self.getWantedResolutionPlaylist(None)

    def getPlaylistVariants(self, url):
        hosts = ['org', 'com', 'net']
        random.shuffle(hosts)
        m3u8_doc = None
        url = None
        for host in hosts:
            candidate_url = "https://edge-hls.{host}/hls/{id}{vr}/master/{id}{vr}{auto}.m3u8".format(
                    host='doppiocdn.' + host,
                    id=self.room_id,
                    vr='_vr' if self.vr else '',
                    auto='_auto' if not self.vr else ''
                )
            try:
                result = self.session.get(
                    candidate_url,
                    headers=self.headers,
                    cookies=self.cookies,
                    timeout=8,
                )
                if result.status_code != 200:
                    continue
                candidate_doc = result.content.decode("utf-8")
                if '#EXTM3U' not in candidate_doc:
                    continue
                m3u8_doc = candidate_doc
                url = candidate_url
                break
            except Exception:
                continue

        if m3u8_doc is None:
            self.log('Failed to fetch a valid StripChat HLS master playlist')
            return []

        mouflon_choices = StripChat._getMouflonChoices(m3u8_doc)
        psch, pkey, pdkey = (
            mouflon_choices[0] if mouflon_choices else (None, None, None)
        )
        if pdkey is None:
            psch, pkey, pdkey = StripChat._getMouflonFromM3U(m3u8_doc)
        if pdkey is None:
            if pkey:
                self.debug(f'StripChat Mouflon key {pkey} is not cached yet')
                StripChat.scheduleMouflonRefresh(max_age=300)
            else:
                self.log(f'Failed to detect Mouflon playlist fields')
            self.log(f'StripChat download paused: Mouflon decryption key unavailable')
            return []
        variants = super().getPlaylistVariants(m3u_data=m3u8_doc)
        return [variant | {'url': f'{variant["url"]}{"&" if "?" in variant["url"] else "?"}psch={psch}&pkey={pkey}'}
                for variant in variants]

    def _getStatusSession(self):
        # Plain requests (not the curl_cffi session used by Bot) - the ID based
        # API answers 418 when requests are made with browser TLS impersonation.
        if self._statusSession is None:
            self._statusSession = requests.Session()
            self._statusSession.headers.update(self.headers | self.html_headers)
        return self._statusSession

    def _resolveUserId(self, username, refresh=False):
        cache_key = username.lower()
        if not refresh and cache_key == self.username.lower() and self.room_id:
            return self.room_id
        if not refresh and cache_key in StripChat._user_id_cache:
            return StripChat._user_id_cache[cache_key]

        r = self._getStatusSession().get(
            f'https://stripchat.com/api/front/users/user-ids/{username}',
            timeout=10
        )
        if r.status_code == 404:
            StripChat._user_id_cache.pop(cache_key, None)
            return None
        r.raise_for_status()
        data = r.json()
        _id = data.get('id') if isinstance(data, dict) else None
        if not _id:
            return None
        _id = str(_id)
        StripChat._user_id_cache[cache_key] = _id
        return _id

    def _getStatusData(self, username):
        try:
            user_id = self._resolveUserId(username)
            if user_id is None:
                self.log('No user ID found')
                return None

            r = self._getStatusSession().get(
                f'https://stripchat.com/api/front/v2/models/{user_id}/cam',
                timeout=10
            )
            if r.status_code == 404:
                # The cached ID can be stale (room renamed or recreated), retry once.
                user_id = self._resolveUserId(username, refresh=True)
                if user_id is None:
                    self.log('No user ID found')
                    return None
                r = self._getStatusSession().get(
                    f'https://stripchat.com/api/front/v2/models/{user_id}/cam',
                    timeout=10
                )
            if r.status_code != 200:
                self.log(f'Status API returned HTTP {r.status_code}')
                return None
            data = r.json()
        except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
            self.log(f'Failed to get status data: {e}')
            return None

        if self.room_id != user_id:
            self.logger.debug(f'Updated room ID: {user_id}')
            self.room_id = user_id
        return data

    def _update_lastInfo(self, data):
        if data is None:
            return None
        if 'cam' not in data:
            if 'error' in data:
                error = data['error']
                if error == 'Not Found':
                    return Status.NOTEXIST
                elif error == 'Model not found':
                    if 'newUsername' in data['data']:
                        _new_username = data['data']['newUsername']
                        self.logger.info(f'Model name changed, new name: {_new_username}')
                        _old_dl_dir = self.outputFolder
                        self.setUsername(_new_username)
                        data = self._getStatusData(_new_username)
                        _error = self._update_lastInfo(data)
                        _new_dl_dir = self.outputFolder
                        if os.path.exists(_old_dl_dir) and not os.path.exists(_new_dl_dir):
                            os.rename(_old_dl_dir, _new_dl_dir)
                        return _error
                    return Status.NOTEXIST
                self.logger.warn(f'Status returned error: {error}')
            return Status.UNKNOWN

        self.lastInfo = {'model': data['user']['user']}
        if isinstance(data['cam'], dict):
            self.lastInfo |= data['cam']
        return None

    def getRoomIdFromUsername(self, username):
        if username == self.username and self.room_id is not None:
            return self.room_id

        try:
            _id = self._resolveUserId(username)
        except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
            self.log(f'Failed to get room ID: {e}')
            return None
        if _id is None:
            self.log('No user ID found')
        return _id

    def getStatus(self):
        data = self._getStatusData(self.username)
        if data is None:
            return Status.UNKNOWN

        error = self._update_lastInfo(data)
        if error:
            return error

        if 'user' in data and 'user' in data['user']:
            model_data = data['user']['user']
            if model_data.get('gender'):
                self.gender = StripChat._GENDER_MAP.get(model_data.get('gender'))

            if model_data.get('country'):
                self.country = model_data.get('country', '').upper()
            elif model_data.get('languages'):
                for lang in model_data['languages']:
                    if lang.upper() in COUNTRIES:
                        self.country = lang.upper()
                        break

        status = self.lastInfo['model'].get('status')
        if status == "public" and self.lastInfo["isCamAvailable"] and self.lastInfo["isCamActive"]:
            return Status.PUBLIC
        if status in self._PRIVATE_STATUSES:
            return Status.PRIVATE
        if status in self._OFFLINE_STATUSES:
            return Status.OFFLINE
        if self.lastInfo['model'].get('isDeleted') is True:
            return Status.NOTEXIST
        if data['user'].get('isGeoBanned') is True:
            return Status.RESTRICTED
        self.logger.warn(f'Got unknown status: {status}')
        return Status.UNKNOWN

    @classmethod
    def getStatusBulk(cls, streamers):
        model_ids = {}
        for streamer in streamers:
            if not isinstance(streamer, StripChat):
                continue
            if streamer.room_id:
                model_ids[streamer.room_id] = streamer

        base_url = 'https://stripchat.com/api/front/models/list?'
        batch_num = 100
        data_map = {}
        model_id_list = list(model_ids)
        for _batch_ids in [model_id_list[i:i+batch_num] for i in range(0, len(model_id_list), batch_num)]:
            session = requests.Session()
            session.headers.update(cls.headers)
            r = session.get(base_url + '&'.join(f'modelIds[]={model_id}' for model_id in _batch_ids), timeout=10)

            if r.status_code != 200:
                print(f'Status API returned HTTP {r.status_code}')
                return
            try:
                data = r.json()
            except (requests.exceptions.JSONDecodeError, json.JSONDecodeError):
                print('Failed to parse JSON response')
                return
            data_map |= {str(model['id']): model for model in data.get('models', [])}

        for model_id, streamer in model_ids.items():
            model_data = data_map.get(model_id)
            if not model_data:
                streamer.setStatus(Status.UNKNOWN)
                continue
            if model_data.get('gender'):
                streamer.gender = cls._GENDER_MAP.get(model_data.get('gender'))
            if model_data.get('country'):
                streamer.country = model_data.get('country', '').upper()
            status = model_data.get('status')
            if status == "public" and model_data.get("isOnline"):
                streamer.setStatus(Status.PUBLIC)
            elif status in cls._PRIVATE_STATUSES:
                streamer.setStatus(Status.PRIVATE)
            elif status in cls._OFFLINE_STATUSES:
                streamer.setStatus(Status.OFFLINE)
            else:
                print(f'[{streamer.siteslug}] {streamer.username}: Bulk update got unknown status: {status}')
                streamer.setStatus(Status.UNKNOWN)
