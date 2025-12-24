import itertools
import random
import re
import time
import requests
import base64
import hashlib
import os
from functools import lru_cache
from typing import Optional, Tuple, List, Dict

from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from streamonitor.bot import Bot
from streamonitor.downloaders.hls import getVideoNativeHLS
from streamonitor.enums import Status


class StripChat(Bot):
    site = "StripChat"
    siteslug = "SC"

    _static_data = None
    _main_js_data = None
    _doppio_js_data = None
    _mouflon_keys: dict = {"Zeechoej4aleeshi": "ubahjae7goPoodi6"}
    _session = None
    
    _DOPPIO_INDEX_PATTERN = re.compile(r'(\d+):\s*"([a-f0-9]+)"')
    _DOPPIO_REQUIRE_PATTERN = re.compile(r'require\(["\']\./(Doppio[^"\']+\.js)["\']\)')
    _HASH_PATTERNS = [
        re.compile(r'{}:\\"([a-zA-Z0-9]{{20}})\\"'),
        re.compile(r'{}:"([a-zA-Z0-9]{{20}})"'),
        re.compile(r'"{}":"([a-zA-Z0-9]{{20}})"'),
    ]
    
    _MOUFLON_NEEDLE = "#EXT-X-MOUFLON:"
    _MOUFLON_FILE_ATTR = "#EXT-X-MOUFLON:FILE:"
    _MOUFLON_FILENAME = "media.mp4"
    _CDN_DOMAINS = ("org", "com", "net")
    _CHARSET = "abcdefghijklmnopqrstuvwxyz0123456789"
    
    _PRIVATE_STATUSES = frozenset(["private", "groupShow", "p2p", "virtualPrivate", "p2pVoice"])
    _OFFLINE_STATUSES = frozenset(["off", "idle"])

    __slots__ = ('vr',)

    def __init__(self, username):
        if StripChat._static_data is None:
            StripChat._static_data = {}
            try:
                self.getInitialData()
            except Exception as e:
                StripChat._static_data = None
                raise e
        
        end_time = time.time() + 15
        while StripChat._static_data == {} and time.time() < end_time:
            time.sleep(0.01)
        
        if StripChat._static_data == {}:
            raise TimeoutError("Static data initialization timeout")
        
        super().__init__(username)
        self.vr = False
        self.getVideo = lambda _, url, filename: getVideoNativeHLS(
            self, url, filename, StripChat.m3u_decoder
        )

    @classmethod
    def _get_session(cls):
        if cls._session is None:
            cls._session = requests.Session()
            retry = Retry(
                total=2,
                backoff_factor=0.1,
                status_forcelist=[429, 500, 502, 503, 504],
            )
            adapter = HTTPAdapter(
                max_retries=retry,
                pool_connections=15,
                pool_maxsize=30,
                pool_block=False
            )
            cls._session.mount("http://", adapter)
            cls._session.mount("https://", adapter)
            cls._session.headers.update({
                'Connection': 'keep-alive',
                'Accept-Encoding': 'gzip, deflate'
            })
        return cls._session

    @classmethod
    def getInitialData(cls):
        s = cls._get_session()

        r = s.get(
            "https://hu.stripchat.com/api/front/v3/config/static",
            headers=cls.headers,
            timeout=5
        )
        r.raise_for_status()
        StripChat._static_data = r.json()["static"]
        
        features = StripChat._static_data["features"]
        mmp_origin = features["MMPExternalSourceOrigin"]
        mmp_version = StripChat._static_data["featuresV2"]["playerModuleExternalLoading"]["mmpVersion"]

        # ❗ FIX: removed duplicate "v"
        mmp_base = f"{mmp_origin}/{mmp_version}"

        # Fetch main.js
        r = s.get(f"{mmp_base}/main.js", headers=cls.headers, timeout=5)
        r.raise_for_status()
        StripChat._main_js_data = r.text
        
        doppio_url = None
        
        if match := cls._DOPPIO_REQUIRE_PATTERN.search(StripChat._main_js_data):
            doppio_url = f"{mmp_base}/{match[1]}"
        elif match := cls._DOPPIO_INDEX_PATTERN.search(StripChat._main_js_data):
            idx = match[1]
            for pattern_template in cls._HASH_PATTERNS:
                pattern = re.compile(pattern_template.pattern.format(idx))
                if hash_match := pattern.search(StripChat._main_js_data):
                    doppio_url = f"{mmp_base}/chunk-{hash_match[1]}.js"

                    break
        
        if not doppio_url:
            raise Exception("Doppio.js not found")
        
        r = s.get(doppio_url, headers=cls.headers, timeout=5)
        r.raise_for_status()
        StripChat._doppio_js_data = r.text

    @staticmethod
    def uniq(length: int = 16) -> str:
        # ❗ FIX: restored exactly as originally present
        return ''.join(random.choices("abcdefghijklmnopqrstuvwxyz0123456789", k=length))

    @classmethod
    @lru_cache(maxsize=512)
    def _get_hash_bytes(cls, key: str) -> bytes:
        return hashlib.sha256(key.encode()).digest()

    @classmethod
    def m3u_decoder(cls, content: str) -> str:
        @lru_cache(maxsize=64)
        def _decode(encrypted_b64: str, key: str) -> str:
            hash_bytes = cls._get_hash_bytes(key)
            data = base64.b64decode(encrypted_b64 + "==")
            return bytes(a ^ b for a, b in zip(data, itertools.cycle(hash_bytes))).decode()
        
        psch, pkey, pdkey = cls._getMouflonFromM3U(content)
        if not pdkey:
            return content
        
        lines = content.split('\n')
        decoded = []
        last_decoded = None
        
        for line in lines:
            if line.startswith(cls._MOUFLON_FILE_ATTR):
                last_decoded = _decode(line[len(cls._MOUFLON_FILE_ATTR):], pdkey)
            elif last_decoded and line.endswith(cls._MOUFLON_FILENAME):
                decoded.append(line.replace(cls._MOUFLON_FILENAME, last_decoded))
                last_decoded = None
            else:
                decoded.append(line)
        
        return '\n'.join(decoded)

    @classmethod
    @lru_cache(maxsize=128)
    def getMouflonDecKey(cls, pkey: str) -> Optional[str]:
        if pkey in cls._mouflon_keys:
            return cls._mouflon_keys[pkey]
        
        pattern = f'"{pkey}:'
        idx = cls._doppio_js_data.find(pattern)
        if idx != -1:
            start = idx + len(pattern)
            end = cls._doppio_js_data.find('"', start)
            if end != -1:
                key = cls._doppio_js_data[start:end]
                cls._mouflon_keys[pkey] = key
                return key
        
        return None

    @staticmethod
    def _getMouflonFromM3U(m3u8_doc: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        needle = StripChat._MOUFLON_NEEDLE
        idx = 0
        
        while (idx := m3u8_doc.find(needle, idx)) != -1:
            line_end = m3u8_doc.find('\n', idx)
            if line_end == -1:
                line_end = len(m3u8_doc)
            
            line = m3u8_doc[idx:line_end]
            parts = line.split(':', 3)
            
            if len(parts) >= 4:
                psch, pkey = parts[2], parts[3]
                if pdkey := StripChat.getMouflonDecKey(pkey):
                    return psch, pkey, pdkey
            
            idx += len(needle)
        
        return None, None, None

    def getWebsiteURL(self) -> str:
        return f"https://stripchat.com/{self.username}"

    def getVideoUrl(self):
        return self.getWantedResolutionPlaylist(None)

    def getPlaylistVariants(self, url) -> List[Dict]:
        stream_id = self.lastInfo["streamName"]
        vr = "_vr" if self.vr else ""
        auto = "_auto" if not self.vr else ""
        
        host = f"doppiocdn.{random.choice(self._CDN_DOMAINS)}"
        url = f"https://edge-hls.{host}/hls/{stream_id}{vr}/master/{stream_id}{vr}{auto}.m3u8"
        
        try:
            result = self.session.get(url, headers=self.headers, cookies=self.cookies, timeout=4)
            result.raise_for_status()
        except:
            return []
        
        m3u8_doc = result.text
        psch, pkey, pdkey = self._getMouflonFromM3U(m3u8_doc)
        
        variants = super().getPlaylistVariants(m3u_data=m3u8_doc)
        
        if not psch or not pkey:
            return variants
        
        params = f"{'&' if '?' in variants[0]['url'] else '?'}psch=v1&pkey={pkey}"
        return [dict(v, url=f"{v['url']}{params}") for v in variants]

    def getStatus(self) -> Status:
        url = f"https://stripchat.com/api/front/v2/models/username/{self.username}/cam?uniq={self.uniq()}"
        
        try:
            r = self.session.get(url, headers=self.headers, timeout=4)
            r.raise_for_status()
            data = r.json()
        except:
            return Status.UNKNOWN
        
        if "cam" not in data:
            if data.get("error") == "Not Found":
                return Status.NOTEXIST
            return Status.UNKNOWN
        
        self.lastInfo = {"model": data["user"]["user"]}
        if isinstance(data["cam"], dict):
            self.lastInfo.update(data["cam"])
        
        status = self.lastInfo["model"].get("status")
        
        if status == "public" and self.lastInfo.get("isCamAvailable") and self.lastInfo.get("isCamActive"):
            return Status.PUBLIC
        
        if status in self._PRIVATE_STATUSES:
            return Status.PRIVATE
        
        if status in self._OFFLINE_STATUSES:
            return Status.OFFLINE
        
        if self.lastInfo["model"].get("isDeleted"):
            return Status.NOTEXIST
        
        if data["user"].get("isGeoBanned"):
            return Status.RESTRICTED
        
        return Status.UNKNOWN
