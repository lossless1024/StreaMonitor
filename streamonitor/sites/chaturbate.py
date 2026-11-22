import os
import re
import tempfile
import time
from pathlib import Path
from urllib.parse import urljoin

import m3u8
import requests

from streamonitor.bot import Bot
from streamonitor.enums import Status, Gender
from streamonitor.utils.playlist_health import inspect_and_report
from parameters import CB_MASTER_PLAYLIST


class Chaturbate(Bot):
    site = 'Chaturbate'
    siteslug = 'CB'
    bulk_update = True

    _GENDER_MAP = {
        'f': Gender.FEMALE,
        'm': Gender.MALE,
        's': Gender.TRANS,
        'c': Gender.BOTH,
    }

    def __init__(self, username):
        super().__init__(username)
        self.sleep_on_offline = 30
        self.sleep_on_error = 60
    
    def getWebsiteURL(self):
        return "https://www.chaturbate.com/" + self.username
    
    def getVideoUrl(self):
        url = self.lastInfo.get('url') if self.lastInfo else None
        if not url:
            self.getStatus()
            url = self.lastInfo.get('url') if self.lastInfo else None
        if not url:
            return None

        # LL-HLS (CMAF) streams – handled by the existing CMAF logic
        if 'llhls.m3u8' in url:
            return self._getCmafPlaylist(url)

        # Edge CMAF variant handling (already present in original logic)
        if self.lastInfo.get('cmaf_edge'):
            url = url.replace('playlist.m3u8', 'playlist_sfm4s.m3u8')
            url = re.sub('live-.+amlst', 'live-c-fhls/amlst', url)

        # For standard HLS master playlists, optionally rewrite to include matching audio
        if CB_MASTER_PLAYLIST:
            rewritten = self._rewriteHlsMaster(url)
            if rewritten:
                return rewritten

        # Fallback: pick the wanted resolution variant from the (possibly rewritten) URL
        return self.getWantedResolutionPlaylist(url)

    def _getCmafPlaylist(self, url):
        if not CB_MASTER_PLAYLIST:
            self.logger.debug("CMAF master playlist rewrite disabled, using master URL")
            return url

        try:
            result = self.session.get(url, headers=self.headers, cookies=self.cookies, timeout=10)
            if result.status_code != 200:
                self.logger.warning(
                    f"Could not fetch CMAF master playlist (HTTP {result.status_code}), falling back to master URL")
                return url

            master = m3u8.loads(result.text)
            inspect_and_report(
                self.logger,
                self.siteslug,
                url,
                result.text,
            )
            if not master.is_variant:
                self.logger.debug("CMAF playlist is not a master playlist, falling back to its URL")
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
                resolution = stream_info.resolution if type(stream_info.resolution) is tuple else (0, 0)
                variants.append({
                    'url': urljoin(url, playlist.uri),
                    'resolution': resolution,
                    'frame_rate': stream_info.frame_rate,
                    'bandwidth': stream_info.bandwidth,
                    'codecs': getattr(stream_info, 'codecs', None),
                    'audio_group': getattr(stream_info, 'audio', None),
                })

            if not variants:
                self.logger.warning("CMAF master playlist has no variants, falling back to master URL")
                return url

            selected = self._selectSource(variants)
            if selected is None:
                return url

            if selected['resolution'][1] != 0:
                frame_rate = ''
                if selected['frame_rate'] is not None and selected['frame_rate'] != 0:
                    frame_rate = f" {selected['frame_rate']}fps"
                self.logger.info(
                    f"Selected {selected['resolution'][0]}x{selected['resolution'][1]}{frame_rate} resolution (CMAF)")

            audio_group = selected['audio_group']
            media = audio_media.get(audio_group) if audio_group else None
            if media is None:
                self.logger.warning(
                    "No matching audio group in CMAF master playlist, falling back to master URL")
                return url

            content = self._buildMasterPlaylist(master, selected, media)
            return self._writeMasterPlaylist(content)
        except Exception as e:
            self.logger.warning(
                f"Failed to build local CMAF master playlist ({e}), falling back to master URL")
            return url

    @staticmethod
    def _buildMasterPlaylist(master, variant, media):
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
        frame_rate = variant.get('frame_rate')
        if frame_rate:
            try:
                stream_attrs.append(f'FRAME-RATE={float(frame_rate):.3f}')
            except (TypeError, ValueError):
                stream_attrs.append(f'FRAME-RATE={frame_rate}')
        if variant.get('codecs'):
            stream_attrs.append(f'CODECS="{variant["codecs"]}"')
        stream_attrs.append(f'AUDIO="{variant["audio_group"]}"')
        lines.append('#EXT-X-STREAM-INF:' + ','.join(stream_attrs))
        lines.append(variant['url'])

        return '\n'.join(lines) + '\n'

    @staticmethod
    def _writeMasterPlaylist(content):
        fd, path = tempfile.mkstemp(prefix='streamonitor-cb-', suffix='.m3u8')
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
    
    def _rewriteHlsMaster(self, url):
        """Rewrite a standard HLS master playlist to include matching audio.

        If ``CB_MASTER_PLAYLIST`` is True, this method downloads the master
        playlist, selects the best video variant (using the existing
        ``_selectSource`` helper), finds the corresponding audio group, and
        builds a new local master playlist that references both the chosen
        video and its audio rendition. The temporary playlist file path is
        returned so that ffmpeg can read it. If any step fails, ``None`` is
        returned and the original URL is used.
        """
        if not CB_MASTER_PLAYLIST:
            return None
        try:
            result = self.session.get(url, headers=self.headers, cookies=self.cookies, timeout=10)
            if result.status_code != 200:
                self.logger.warning(
                    f"Could not fetch HLS master playlist (HTTP {result.status_code}), falling back to original URL"
                )
                return None
            master = m3u8.loads(result.text)
            inspect_and_report(
                self.logger,
                self.siteslug,
                url,
                result.text,
            )
            if not master.is_variant:
                self.logger.debug("HLS playlist is not a master playlist, using original URL")
                return None
            # Collect audio renditions
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
            # Collect video variants
            variants = []
            for playlist in master.playlists:
                stream_info = playlist.stream_info
                resolution = stream_info.resolution if isinstance(stream_info.resolution, tuple) else (0, 0)
                variants.append({
                    'url': urljoin(url, playlist.uri),
                    'resolution': resolution,
                    'frame_rate': getattr(stream_info, 'frame_rate', None),
                    'bandwidth': getattr(stream_info, 'bandwidth', None),
                    'codecs': getattr(stream_info, 'codecs', None),
                    'audio_group': getattr(stream_info, 'audio', None),
                })
            if not variants:
                self.logger.warning("HLS master playlist has no variants, falling back to original URL")
                return None
            selected = self._selectSource(variants)
            if selected is None:
                return None
            audio_group = selected.get('audio_group')
            media = audio_media.get(audio_group) if audio_group else None
            if media is None:
                self.logger.warning("No matching audio group in HLS master playlist, falling back to original URL")
                return None
            content = self._buildMasterPlaylist(master, selected, media)
            return self._writeMasterPlaylist(content)
        except Exception as e:
            self.logger.warning(f"Failed to rewrite HLS master playlist ({e}), falling back to original URL")
            return None

    @staticmethod
    def _parseStatus(status):
        if status == "public":
            return Status.PUBLIC
        elif status in ["private", "hidden"]:
            return Status.PRIVATE
        else:
            return Status.OFFLINE

    def getStatus(self):
        headers = {"X-Requested-With": "XMLHttpRequest"}
        data = {"room_slug": self.username, "bandwidth": "high"}

        try:
            r = self.session.post("https://chaturbate.com/get_edge_hls_url_ajax/", headers=headers, data=data, timeout=10)
            if r.status_code == 429:
                self.ratelimit = True
                return Status.RATELIMIT
            elif r.status_code == 404:
                self.ratelimit = False
                return Status.NOTEXIST
            elif r.status_code != 200:
                self.logger.warning(f"Unexpected status code {r.status_code} from get_edge_hls_url_ajax")
                self.ratelimit = False
                return Status.UNKNOWN
            self.lastInfo = r.json()
            status = self._parseStatus(self.lastInfo.get('room_status'))
            if status == Status.PUBLIC and not self.lastInfo.get('url'):
                status = Status.RESTRICTED
            self.ratelimit = False
            return status
        except Exception as e:
            self.logger.warning(f"Error checking status for {self.username}: {e}")
            self.ratelimit = False
            return Status.UNKNOWN

    _last_bulk_data = None
    _last_bulk_time = 0

    @classmethod
    def getStatusBulk(cls, streamers):
        cb_streamers = [s for s in streamers if isinstance(s, Chaturbate)]
        if not cb_streamers:
            return

        now = time.time()
        if cls._last_bulk_data is not None and (now - cls._last_bulk_time) < 10:
            data_map = cls._last_bulk_data
        else:
            session = requests.Session()
            session.headers.update(cls.headers)
            try:
                r = session.get("https://chaturbate.com/affiliates/api/onlinerooms/?format=json&wm=DkfRj", timeout=15)
                if r.status_code != 200:
                    print(f"[CB] Bulk API request failed with HTTP {r.status_code}")
                    return
                data = r.json()
                data_map = {str(model['username']).lower(): model for model in data}
                cls._last_bulk_data = data_map
                cls._last_bulk_time = now
            except Exception as e:
                print(f"[CB] Failed to fetch or parse bulk JSON: {e}")
                if cls._last_bulk_data is not None:
                    data_map = cls._last_bulk_data
                else:
                    return

        for streamer in cb_streamers:
            model_data = data_map.get(streamer.username.lower())
            if not model_data:
                streamer.setStatus(Status.OFFLINE)
                continue
            if model_data.get('gender'):
                streamer.gender = cls._GENDER_MAP.get(model_data.get('gender'))
            if model_data.get('country'):
                streamer.country = model_data.get('country', '').upper()
            status = cls._parseStatus(model_data['current_show'])
            if status == Status.PUBLIC:
                if streamer.sc in [Status.PUBLIC, Status.RESTRICTED]:
                    continue
                status = streamer.getStatus()
            if status == Status.UNKNOWN:
                print(f'[{streamer.siteslug}] {streamer.username}: Bulk update got unknown status: {status}')
            streamer.setStatus(status)
