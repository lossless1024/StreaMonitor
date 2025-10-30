import itertools
import random
import re
import time
import requests
import base64
import hashlib
import urllib.parse

from streamonitor.bot import Bot
from streamonitor.downloaders.hls import getVideoNativeHLS
from streamonitor.enums import Status


class StripChat(Bot):
    site = 'StripChat'
    siteslug = 'SC'

    _static_data = None
    _main_js_data = None
    _doppio_js_data = None
    _mouflon_keys: dict = None
    _cached_keys: dict[str, bytes] = None

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
        self.getVideo = lambda _, url, filename: getVideoNativeHLS(self, url, filename, StripChat.m3u_decoder)

    @classmethod
    def getInitialData(cls):
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
        # Populate Mouflon keys from Doppio.js using a generic regex
        StripChat._populateMouflonKeysFromDoppio()

    @classmethod
    def _populateMouflonKeysFromDoppio(cls):
        """Extracts pkey:decode_key pairs from Doppio.js using a generic regex.
        Enables dynamic pkey discovery without relying on fixed values."""
        try:
            if not cls._doppio_js_data:
                return
            if cls._mouflon_keys is None:
                cls._mouflon_keys = {}
            pattern = r"\b[A-Za-z0-9]{12,}:[A-Za-z0-9]{12,}\b"
            matches = re.findall(pattern, cls._doppio_js_data)
            for m in matches:
                left, right = m.split(":", 1)
                if left and right and left not in cls._mouflon_keys:
                    cls._mouflon_keys[left] = right
        except Exception:
            pass

    @classmethod
    def m3u_decoder(cls, content):
        _mouflon_file_attr = "#EXT-X-MOUFLON:FILE:"
        _mouflon_filename = 'media.mp4'

        def _decode(encrypted_b64: str, key: str) -> str:
            if cls._cached_keys is None:
                cls._cached_keys = {}
            hash_bytes = cls._cached_keys[key] if key in cls._cached_keys \
                else cls._cached_keys.setdefault(key, hashlib.sha256(key.encode("utf-8")).digest())
            encrypted_data = base64.b64decode(encrypted_b64 + "==")
            return bytes(a ^ b for (a, b) in zip(encrypted_data, itertools.cycle(hash_bytes))).decode("utf-8")

        # Extract Mouflon from M3U8; if pkey is missing or unmapped, choose one detected from Doppio
        psch, pkey = StripChat._getMouflonFromM3U(content)
        if not psch and pkey:
            psch = 'v1'
        # Ensure we have a valid pkey that exists in the detected mapping
        cls._populateMouflonKeysFromDoppio()
        if not pkey or (cls._mouflon_keys and pkey not in cls._mouflon_keys):
            try:
                candidates = list(cls._mouflon_keys.keys()) if cls._mouflon_keys else []
                chosen = None
                for c in candidates:
                    if c.lower().startswith('zokee'):
                        chosen = c
                        break
                if not chosen and candidates:
                    chosen = candidates[0]
                pkey = chosen
            except Exception:
                pkey = None

        def _append_params(url: str) -> str:
            try:
                p = urllib.parse.urlsplit(url)
                if not ('doppiocdn.com' in p.netloc or 'doppiocdn.net' in p.netloc or 'doppiocdn.org' in p.netloc):
                    return url
                q = urllib.parse.parse_qs(p.query, keep_blank_values=True)
                changed = False
                if psch and 'psch' not in q:
                    q['psch'] = [psch]
                    changed = True
                if pkey and 'pkey' not in q:
                    q['pkey'] = [pkey]
                    changed = True
                if not changed:
                    return url
                new_q = urllib.parse.urlencode({k: v[0] for k, v in q.items()})
                return urllib.parse.urlunsplit((p.scheme, p.netloc, p.path, new_q, p.fragment))
            except Exception:
                return url

        decoded = ''
        lines = content.splitlines()
        last_decoded_file = None
        for line in lines:
            if line.startswith(_mouflon_file_attr):
                if pkey:
                    last_decoded_file = _decode(line[len(_mouflon_file_attr):], cls.getMouflonDecKey(pkey))
                else:
                    last_decoded_file = None
            elif line.endswith(_mouflon_filename) and last_decoded_file:
                replaced = line.replace(_mouflon_filename, last_decoded_file)
                decoded += _append_params(replaced) + '\n'
                last_decoded_file = None
            elif line.startswith('#EXT-X-MAP:'):
                m = re.search(r'URI="([^"]+)"', line)
                if m:
                    new_uri = _append_params(m.group(1))
                    line = re.sub(r'URI="([^"]+)"', f'URI="{new_uri}"', line)
                decoded += line + '\n'
            elif line.startswith('#EXT-X-PART:'):
                m = re.search(r'URI="([^"]+)"', line)
                if m:
                    new_uri = _append_params(m.group(1))
                    line = re.sub(r'URI="([^"]+)"', f'URI="{new_uri}"', line)
                decoded += line + '\n'
            elif line.startswith('http://') or line.startswith('https://'):
                decoded += _append_params(line) + '\n'
            else:
                decoded += line + '\n'
        return decoded

    @classmethod
    def getMouflonDecKey(cls, pkey):
        if cls._mouflon_keys is None:
            cls._mouflon_keys = {}
        if pkey in cls._mouflon_keys:
            return cls._mouflon_keys[pkey]
        # Try populating from Doppio if not present yet
        cls._populateMouflonKeysFromDoppio()
        if pkey in cls._mouflon_keys:
            return cls._mouflon_keys[pkey]
        # Fallback to specific pattern if the generic did not find it
        match = re.findall(f'"{pkey}:(.*?)"', cls._doppio_js_data)
        if match:
            cls._mouflon_keys[pkey] = match[0]
            return match[0]
        # As a last resort, return a decode key for a detected pkey
        candidates = list(cls._mouflon_keys.keys()) if cls._mouflon_keys else []
        for c in candidates:
            if c.lower().startswith('zokee'):
                return cls._mouflon_keys[c]
        if candidates:
            return cls._mouflon_keys[candidates[0]]
        raise KeyError(f"Mouflon decode key not found and no detected keys available for pkey={pkey}")

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
                host='doppiocdn.' + random.choice(['org', 'com', 'net']),
                id=self.lastInfo["streamName"],
                vr='_vr' if self.vr else '',
                auto='_auto' if not self.vr else ''
            )
        # Strengthen critical headers for the master request
        headers = dict(self.headers)
        headers.setdefault('Referer', self.getWebsiteURL())
        headers.setdefault('Origin', 'https://stripchat.com')
        result = requests.get(url, headers=headers, cookies=self.cookies)
        m3u8_doc = result.content.decode("utf-8")
        psch, pkey = StripChat._getMouflonFromM3U(m3u8_doc)
        if not psch and pkey:
            psch = 'v1'
        # Ensure pkey maps to a decode key; override with detected if unmapped/missing
        StripChat._populateMouflonKeysFromDoppio()
        if not pkey or (StripChat._mouflon_keys and pkey not in StripChat._mouflon_keys):
            candidates = list(StripChat._mouflon_keys.keys()) if StripChat._mouflon_keys else []
            chosen = None
            for c in candidates:
                if c.lower().startswith('zokee'):
                    chosen = c
                    break
            if not chosen and candidates:
                chosen = candidates[0]
            pkey = chosen
        variants = super().getPlaylistVariants(m3u_data=m3u8_doc)
        # Append psch/pkey when available
        if psch and pkey:
            return [
                variant | {'url': f'{variant["url"]}{"&" if "?" in variant["url"] else "?"}psch={psch}&pkey={pkey}'}
                for variant in variants
            ]
        return variants

    @staticmethod
    def uniq(length=16):
        chars = ''.join(chr(i) for i in range(ord('a'), ord('z')+1))
        chars += ''.join(chr(i) for i in range(ord('0'), ord('9')+1))
        return ''.join(random.choice(chars) for _ in range(length))

    def getStatus(self):
        r = requests.get(
            f'https://stripchat.com/api/front/v2/models/username/{self.username}/cam?uniq={StripChat.uniq()}',
            headers=self.headers
        )

        try:
            data = r.json()
        except requests.exceptions.JSONDecodeError:
            self.log('Failed to parse JSON response')
            return Status.UNKNOWN

        if 'cam' not in data:
            if 'error' in data:
                error = data['error']
                if error == 'Not Found':
                    return Status.NOTEXIST
                self.logger.warn(f'Status returned error: {error}')
            return Status.UNKNOWN

        self.lastInfo = {'model': data['user']['user']}
        if isinstance(data['cam'], dict):
            self.lastInfo |= data['cam']

        status = self.lastInfo['model'].get('status')
        if status == "public" and self.lastInfo["isCamAvailable"] and self.lastInfo["isCamActive"]:
            return Status.PUBLIC
        if status in ["private", "groupShow", "p2p", "virtualPrivate", "p2pVoice"]:
            return Status.PRIVATE
        if status in ["off", "idle"]:
            return Status.OFFLINE
        if self.lastInfo['model'].get('isDeleted') is True:
            return Status.NOTEXIST
        if data['user'].get('isGeoBanned') is True:
            return Status.RESTRICTED
        self.logger.warn(f'Got unknown status: {status}')
        return Status.UNKNOWN
