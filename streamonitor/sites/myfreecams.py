import json
import os
import random
import re
import tempfile
import time
import urllib.parse
import uuid
from pathlib import Path
from urllib.parse import urljoin

import m3u8
import requests
import websocket

from streamonitor.bot import Bot
from streamonitor.enums import Status, Gender, COUNTRIES
from streamonitor.utils.playlist_health import inspect_and_report
from parameters import CB_MASTER_PLAYLIST


class MyFreeCams(Bot):
    site = 'MyFreeCams'
    siteslug = 'MFC'
    bulk_update = True

    _server_config = None
    _server_config_time = 0

    _default_chat_servers = [
        'wchat74', 'wchat75', 'wchat67', 'wchat14', 'wchat16', 'wchat17',
        'wchat18', 'wchat19', 'wchat21', 'wchat22', 'wchat23', 'wchat24',
        'wchat25', 'wchat26', 'wchat28', 'wchat29', 'wchat30', 'wchat31',
        'wchat32', 'wchat33', 'wchat34', 'wchat35', 'wchat36', 'wchat37',
        'wchat38', 'wchat39', 'wchat40', 'wchat41', 'wchat43', 'wchat44',
        'wchat45', 'wchat46', 'wchat47', 'wchat48', 'wchat49', 'wchat50',
        'wchat51', 'wchat52', 'wchat53', 'wchat54', 'wchat55', 'wchat56',
        'wchat57', 'wchat58', 'wchat59', 'wchat60', 'wchat61', 'wchat62',
        'wchat63', 'wchat64', 'wchat66', 'wchat68', 'wchat69', 'wchat70',
        'wchat71', 'wchat72', 'wchat73'
    ]

    _MG_MAP = {
        0: Gender.FEMALE,
        1: Gender.FEMALE,
        2: Gender.TRANS,
        3: Gender.BOTH,
        4: Gender.MALE
    }

    _COUNTRY_NAME_TO_ISO = {c['name'].lower(): iso for iso, c in COUNTRIES.items()}

    def __init__(self, username):
        super().__init__(username)
        self.sleep_on_offline = 30
        self.sleep_on_error = 30
        self.lastInfo = None

    def getWebsiteURL(self):
        return f"https://www.myfreecams.com/#{self.username}"

    @classmethod
    def getServerConfig(cls, force=False):
        now = time.time()
        if cls._server_config is None or now - cls._server_config_time > 3600 or force:
            try:
                r = requests.get('https://www.myfreecams.com/_js/serverconfig.js', timeout=10)
                if r.status_code == 200:
                    cls._server_config = r.json()
                    cls._server_config_time = now
            except Exception:
                if cls._server_config is None:
                    cls._server_config = {}
        return cls._server_config or {}

    @classmethod
    def _query_models_ws(cls, usernames: list[str]) -> dict[str, dict | None]:
        if not usernames:
            return {}

        config = cls.getServerConfig()
        raw_chat_servers = config.get('chat_servers', [])
        valid_chat_servers = [s for s in raw_chat_servers if re.match(r'^wchat\d+$', s)]
        if not valid_chat_servers:
            valid_chat_servers = cls._default_chat_servers

        results: dict[str, dict | None] = {}
        pending = set(u.lower() for u in usernames)

        candidates = random.sample(valid_chat_servers, min(3, len(valid_chat_servers)))

        for server in candidates:
            if not pending:
                break
            ws = None
            try:
                ws = websocket.create_connection(f'wss://{server}.myfreecams.com/fcsl', timeout=5)
                ws.send('hello fcserver\n\0')
                r_id = uuid.uuid4().hex[:32]
                ws.send(f'1 0 0 20071025 0 {r_id}@guest:guest\n')
                time.sleep(0.3)

                for u in list(pending):
                    ws.send(f'10 0 0 20 0 {u}\n')

                buf = ''
                deadline = time.time() + min(8.0, max(3.0, len(pending) * 0.1))
                while pending and time.time() < deadline:
                    try:
                        ws.settimeout(1.0)
                        chunk = ws.recv()
                        if not chunk:
                            break
                        buf += chunk
                        while len(buf) >= 6:
                            try:
                                msg_len = int(buf[:6])
                            except ValueError:
                                buf = buf[1:]
                                continue
                            if len(buf) < 6 + msg_len:
                                break
                            msg = buf[6 : 6 + msg_len]
                            buf = buf[6 + msg_len :]

                            parts = msg.split(' ', 5)
                            if len(parts) >= 5 and parts[0] == '10':
                                payload = urllib.parse.unquote(parts[5]) if len(parts) > 5 else ''
                                try:
                                    data = json.loads(payload)
                                    nm = str(data.get('nm', '')).lower()
                                    results[nm] = data
                                    pending.discard(nm)
                                except Exception:
                                    nm = payload.strip().lower()
                                    results[nm] = None
                                    pending.discard(nm)
                    except websocket.WebSocketTimeoutException:
                        break
                    except Exception:
                        break
                try:
                    ws.send('99 0 0 0 0\n')
                except Exception:
                    pass
            except Exception:
                pass
            finally:
                if ws:
                    try:
                        ws.close()
                    except Exception:
                        pass

        return results

    @classmethod
    def _parse_model_status(cls, model_data: dict | None) -> Status:
        if model_data is None:
            return Status.NOTEXIST

        vs = model_data.get('vs')
        if vs is None:
            return Status.UNKNOWN

        if vs in (0, 90):
            camserv = model_data.get('u', {}).get('camserv')
            if camserv and int(camserv) > 0:
                return Status.PUBLIC
            return Status.OFFLINE

        if vs in (11, 12, 13, 14, 15, 91, 92, 93, 94):
            return Status.PRIVATE

        if vs in (2, 126, 127):
            return Status.OFFLINE

        return Status.OFFLINE

    @classmethod
    def _update_streamer_info(cls, streamer, model_data: dict):
        streamer.lastInfo = model_data

        u = model_data.get('u', {})
        country = u.get('country')
        if country:
            country_clean = country.strip()
            iso = cls._COUNTRY_NAME_TO_ISO.get(country_clean.lower())
            if iso:
                streamer.country = iso
            elif len(country_clean) == 2 and country_clean.upper() in COUNTRIES:
                streamer.country = country_clean.upper()

        m = model_data.get('m', {})
        mg = m.get('mg')
        if mg in cls._MG_MAP:
            streamer.gender = cls._MG_MAP[mg]

    def getStatus(self):
        results = self._query_models_ws([self.username])
        key = self.username.lower()
        if key not in results:
            return Status.UNKNOWN

        model_data = results[key]
        if model_data is None:
            return Status.NOTEXIST

        self._update_streamer_info(self, model_data)
        return self._parse_model_status(model_data)

    @classmethod
    def getStatusBulk(cls, streamers):
        mfc_streamers = [s for s in streamers if isinstance(s, MyFreeCams)]
        if not mfc_streamers:
            return

        usernames = [s.username for s in mfc_streamers]
        results = cls._query_models_ws(usernames)

        for streamer in mfc_streamers:
            key = streamer.username.lower()
            if key not in results:
                continue

            model_data = results[key]
            if model_data is None:
                streamer.setStatus(Status.NOTEXIST)
                continue

            cls._update_streamer_info(streamer, model_data)
            status = cls._parse_model_status(model_data)
            streamer.setStatus(status)

    def getVideoUrl(self):
        if not self.lastInfo or 'u' not in self.lastInfo:
            status = self.getStatus()
            if status != Status.PUBLIC:
                return None

        uid = self.lastInfo.get('uid')
        u = self.lastInfo.get('u', {})
        camserv = str(u.get('camserv', ''))

        if not uid or not camserv or camserv == '0':
            return None

        config = self.getServerConfig()
        h5 = config.get('h5video_servers', {})
        wzobs = config.get('wzobs_servers', {})
        wzext = config.get('wzext_servers', {})

        is_wz = camserv in wzobs or camserv in wzext
        server = wzobs.get(camserv) or h5.get(camserv) or wzext.get(camserv)

        if not server:
            cs_int = int(camserv)
            if cs_int >= 1800:
                server = f'video{cs_int - 700}'
                is_wz = True
            elif cs_int >= 900:
                server = f'video{cs_int - 500}'
            else:
                return None

        uid_video = 100000000 + int(uid)
        prefix = 'mfc_a_' if is_wz else 'mfc_'

        cmaf_url = (
            f'https://edgevideo.myfreecams.com/llhls/NxServer/{camserv}/'
            f'ngrp:{prefix}{uid_video}.f4v_cmaf/playlist_cmaf.m3u8'
        )
        try:
            r = self.session.get(cmaf_url)
            if r.status_code == 200:
                return self._rewriteCmafPlaylist(cmaf_url)
        except Exception:
            pass

        alt_prefix = 'mfc_' if is_wz else 'mfc_a_'
        alt_cmaf_url = (
            f'https://edgevideo.myfreecams.com/llhls/NxServer/{camserv}/'
            f'ngrp:{alt_prefix}{uid_video}.f4v_cmaf/playlist_cmaf.m3u8'
        )
        try:
            r = self.session.get(alt_cmaf_url)
            if r.status_code == 200:
                return self._rewriteCmafPlaylist(alt_cmaf_url)
        except Exception:
            pass

        playlist_url = f'https://{server}.myfreecams.com/NxServer/ngrp:{prefix}{uid_video}.f4v_mobile/playlist.m3u8'

        try:
            r = self.session.get(playlist_url)
            if r.status_code == 200:
                return self.getWantedResolutionPlaylist(playlist_url)
        except Exception:
            pass

        # Try alternate prefix in case broadcaster OBS flag was inverted
        alt_url = f'https://{server}.myfreecams.com/NxServer/ngrp:{alt_prefix}{uid_video}.f4v_mobile/playlist.m3u8'
        try:
            r = self.session.get(alt_url)
            if r.status_code == 200:
                return self.getWantedResolutionPlaylist(alt_url)
        except Exception:
            pass

        return None

    def _rewriteCmafPlaylist(self, url):
        if not CB_MASTER_PLAYLIST:
            return url

        try:
            result = self.session.get(
                url, headers=self.headers, cookies=self.cookies, timeout=10
            )
            if result.status_code != 200:
                return url

            master = m3u8.loads(result.text)
            inspect_and_report(
                self.logger,
                self.siteslug,
                url,
                result.text,
            )
            if not master.is_variant:
                return url

            audio_media = {}
            for media in master.media:
                if media.type != 'AUDIO' or not media.uri:
                    continue
                audio_media[media.group_id] = {
                    'group_id': media.group_id,
                    'name': media.name,
                    'channels': getattr(media, 'channels', None),
                    'uri': urljoin(url, media.uri),
                }

            variants = []
            for playlist in master.playlists:
                stream_info = playlist.stream_info
                resolution = (
                    stream_info.resolution
                    if isinstance(stream_info.resolution, tuple)
                    else (0, 0)
                )
                variants.append({
                    'url': urljoin(url, playlist.uri),
                    'resolution': resolution,
                    'frame_rate': getattr(stream_info, 'frame_rate', None),
                    'bandwidth': getattr(stream_info, 'bandwidth', None),
                    'codecs': getattr(stream_info, 'codecs', None),
                    'audio_group': getattr(stream_info, 'audio', None),
                })

            if not variants:
                return url

            selected = self._selectSource(variants)
            if selected is None:
                return url

            media = audio_media.get(selected.get('audio_group'))
            if media is None:
                return url

            content = self._buildCmafMasterPlaylist(master, selected, media)
            return self._writeCmafMasterPlaylist(content)
        except Exception as e:
            self.logger.warning(
                f"Failed to build MFC CMAF master playlist ({e}), falling back to master URL"
            )
            return url

    @staticmethod
    def _buildCmafMasterPlaylist(master, variant, media):
        lines = ['#EXTM3U']

        version = getattr(master, 'version', None)
        if version:
            lines.append(f'#EXT-X-VERSION:{version}')
        lines.append('#EXT-X-INDEPENDENT-SEGMENTS')

        media_attrs = [
            'TYPE=AUDIO',
            f'GROUP-ID="{media["group_id"]}"',
        ]
        if media.get('name'):
            media_attrs.append(f'NAME="{media["name"]}"')
        media_attrs.extend(['DEFAULT=YES', 'AUTOSELECT=YES', 'FORCED=NO'])
        if media.get('channels'):
            media_attrs.append(f'CHANNELS="{media["channels"]}"')
        media_attrs.append(f'URI="{media["uri"]}"')
        lines.append('#EXT-X-MEDIA:' + ','.join(media_attrs))

        stream_attrs = [f'BANDWIDTH={variant["bandwidth"]}']
        width, height = variant['resolution']
        if width and height:
            stream_attrs.append(f'RESOLUTION={width}x{height}')
        if variant.get('frame_rate'):
            try:
                stream_attrs.append(
                    f'FRAME-RATE={float(variant["frame_rate"]):.3f}'
                )
            except (TypeError, ValueError):
                stream_attrs.append(f'FRAME-RATE={variant["frame_rate"]}')
        if variant.get('codecs'):
            stream_attrs.append(f'CODECS="{variant["codecs"]}"')
        stream_attrs.append(f'AUDIO="{variant["audio_group"]}"')
        lines.append('#EXT-X-STREAM-INF:' + ','.join(stream_attrs))
        lines.append(variant['url'])

        return '\n'.join(lines) + '\n'

    @staticmethod
    def _writeCmafMasterPlaylist(content):
        fd, path = tempfile.mkstemp(prefix='streamonitor-mfc-', suffix='.m3u8')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as playlist_file:
                playlist_file.write(content)
        except BaseException:
            try:
                os.unlink(path)
            except OSError:
                pass
            raise
        return Path(path)
