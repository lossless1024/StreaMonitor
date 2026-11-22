from __future__ import unicode_literals
import os
import re
import shutil
import subprocess
import time
import traceback
from enum import Enum
from urllib.parse import urljoin

import m3u8
from curl_cffi import requests
from time import sleep
from datetime import datetime
from threading import Thread

from streamonitor.enums import Status, COUNTRIES, Gender, GENDER_DATA
import streamonitor.log as log
from parameters import DOWNLOADS_DIR, DOWNLOADS_BY_DATE, DOWNLOAD_DATE_FORMAT, DEBUG, WANTED_RESOLUTION, WANTED_RESOLUTION_PREFERENCE, CONTAINER, HTTP_USER_AGENT, FFMPEG_PATH, SEGMENT_TIME
from streamonitor.downloaders.ffmpeg import getVideoFfmpeg
from streamonitor.models import VideoData
from streamonitor.utils.playlist_health import inspect_and_report, inspect_playlist

LOADED_SITES = set()


class Bot(Thread):
    site = None
    siteslug = None
    aliases = []
    ratelimit = False
    bulk_update = False

    sleep_on_private = 5
    sleep_on_offline = 5
    sleep_on_long_offline = 300
    sleep_on_error = 20
    sleep_on_ratelimit = 180
    long_offline_timeout = 600

    headers = {
        "User-Agent": HTTP_USER_AGENT
    }

    html_headers = {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Encoding': 'none',
        'Accept-Language': 'en,en-US;q=0.9,en-US;q=0.8,en;q=0.7',
        'Pragma': 'no-cache',
        'Priority': 'u=4',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'cross-site',
        'Sec-Fetch-User': '?1',
        'Upgrade-Insecure-Requests': '1',
    }

    status_messages = {
        Status.UNKNOWN: "Unknown error",
        Status.PUBLIC: "Channel online",
        Status.OFFLINE: "No stream",
        Status.LONG_OFFLINE: "No stream for a while",
        Status.PRIVATE: "Private show",
        Status.RATELIMIT: "Rate limited",
        Status.NOTEXIST: "Nonexistent user",
        Status.NOTRUNNING: "Not running",
        Status.ERROR: "Error on downloading",
        Status.RESTRICTED: "Model is restricted, maybe geo-block"
    }

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

        if cls.site:
            global LOADED_SITES
            LOADED_SITES.add(cls)

    def __init__(self, username):
        super().__init__()
        self.username = username
        self.logger = self.getLogger()

        # Impersonate a browser: some sites (e.g. camsoda) reject curl_cffi's default
        # fingerprint with a 403, which would otherwise surface as a false rate limit.
        self.session = requests.Session(impersonate="chrome")
        self.session.headers.update(self.headers)
        self.cookies = None
        self.cookieUpdater = None
        self.cookie_update_interval = 0

        #this will store the latest status of the current model
        self.previous_status = None

        self.lastInfo = {}  # This dict will hold information about stream after getStatus is called. One can use this in getVideoUrl
        self.running = False
        self.quitting = False
        self.sc: Status = Status.NOTRUNNING  # Status code
        self.getVideo = getVideoFfmpeg
        self.stopDownload = None
        self.recording = False
        self.video_files = []
        self.video_files_total_size = 0
        # A streamer that stays online is one logical recording. When an
        # attempt is interrupted (network error, stalled ffmpeg, expired stream
        # URL) the next attempt continues in a part file. All parts are merged
        # into recording_base once the show is over.
        self.recording_base = None
        self.recording_parts = []
        self._recording_disconnect_at = None
        self.RECONNECT_GRACE_SECONDS = 45
        self._download_date_folder = None
        self._recoveredRecordings = False
        self.cache_file_list()

        self.gender = None
        self.country = None
        self.url = self.getWebsiteURL()

    def setUsername(self, username):
        self.username = username
        self.logger = self.getLogger()
        self.cache_file_list()
        self.url = self.getWebsiteURL()

    def getLogger(self):
        if hasattr(self, 'logger') and self.logger:
            self.logger.removeHandler(self.logger.handlers[0])
        return log.Logger("[" + self.siteslug + "] " + self.username).get_logger()

    def restart(self):
        self.running = True

    def stop(self, a, b, thread_too=False):
        if self.running:
            self.log("Stopping...")
            if self.stopDownload:
                self.stopDownload()
            self.running = False
        if thread_too:
            self.quitting = True

    def getStatus(self):
        return Status.UNKNOWN

    def log(self, message):
        self.logger.info(message)

    def debug(self, message, filename=None):
        if DEBUG:
            self.logger.debug(message)
            if not filename:
                filename = os.path.join(self.outputFolder, 'debug.log')
            with open(filename, 'a+') as debugfile:
                debugfile.write(message + '\n')

    def status(self):
        message = self.status_messages.get(self.sc) or self.status_messages.get(Status.UNKNOWN)
        if self.sc == Status.NOTEXIST:
            self.running = False
        return message

    def getWebsiteURL(self):
        return "javascript:void(0)"

    @property
    def country_data(self):
        return COUNTRIES.get(self.country, {'flag': '', 'name': 'Unknown'})

    @property
    def gender_data(self):
        return GENDER_DATA.get(self.gender, GENDER_DATA.get(Gender.UNKNOWN))

    @property
    def last_stream(self):
        """Unix timestamp of the most recent recording, or 0 if none.

        Derived from recording file mtimes; a currently-recording streamer's
        growing file keeps this near 'now', so it sorts as most recent.
        """
        files = getattr(self, 'video_files', None)
        if not files:
            return 0
        return max((getattr(v, 'mtime', 0) for v in files), default=0)

    def cache_file_list(self):
        videos_folder = self.outputFolder
        _videos = []
        _total_size = 0
        if os.path.isdir(videos_folder):
            try:
                for file in os.scandir(videos_folder):
                    if file.is_dir():
                        continue
                    if not os.path.splitext(file.name)[1][1:] in ['mp4', 'mkv', 'webm', 'mov', 'avi', 'wmv']:
                        continue
                    video = VideoData(file, self.username)
                    _total_size += video.filesize
                    _videos.append(video)
            except Exception as e:
                self.logger.warning(e)
        self.video_files = _videos
        self.video_files_total_size = _total_size

    def nextRecordingFilename(self):
        """Output file for the next recording attempt.

        Consecutive attempts for the same show write part files so the
        recording can be resumed without creating several separate videos.
        """
        if SEGMENT_TIME is not None:
            # ffmpeg writes the segment files itself. Resuming would restart
            # the segment counter, so every attempt keeps its own name.
            return self.genOutFilename()
        if self.recording_base and self.recording_parts:
            stem, ext = os.path.splitext(self.recording_base)
            filename = f'{stem}.part{len(self.recording_parts)}{ext}'
            self.recording_parts.append(filename)
            return filename
        self.recording_base = self.genOutFilename()
        self.recording_parts = [self.recording_base]
        return self.recording_base

    def hasRecordingInProgress(self):
        return bool(self.recording_base and self.recording_parts)

    def reconcileRecordingConnection(self, status, now=None):
        """Keep one show open briefly across temporary reconnect gaps."""
        if not self.hasRecordingInProgress():
            self._recording_disconnect_at = None
            return False

        if status == Status.PUBLIC:
            self._recording_disconnect_at = None
            return False

        if status in (Status.NOTEXIST, Status.LONG_OFFLINE):
            self._recording_disconnect_at = None
            return True

        if status in (
            Status.OFFLINE,
            Status.PRIVATE,
            Status.RESTRICTED,
            Status.ERROR,
            Status.RATELIMIT,
            Status.UNKNOWN,
        ):
            if self._recording_disconnect_at is None:
                self._recording_disconnect_at = time.monotonic() if now is None else now
            disconnected_at = self._recording_disconnect_at
            elapsed = (time.monotonic() if now is None else now) - disconnected_at
            return elapsed >= self.RECONNECT_GRACE_SECONDS

        return False

    def _isReadablePart(self, path):
        """Check that ffmpeg can open a recording part.

        A part that was killed before ffmpeg could write its index is not
        playable and would make the merge stop early.
        """
        try:
            result = subprocess.run(
                [FFMPEG_PATH, '-v', 'error', '-xerror', '-i', path,
                 '-t', '0', '-f', 'null', '-'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as e:
            # Let the merge itself report a missing ffmpeg.
            self.logger.warning(e)
            return True
        return result.returncode == 0

    def finalizeRecording(self):
        """Merge the parts of the current show into a single video file."""
        base = self.recording_base
        parts = self.recording_parts
        self.recording_base = None
        self.recording_parts = []
        self._recording_disconnect_at = None
        if not base or not parts:
            return
        self._consolidateParts(base, parts)

    def _consolidateParts(self, base, parts):
        """Drop empty parts and merge the rest into ``base``.

        Shared by the normal end-of-show merge and the recovery of parts a
        killed process left behind.
        """
        existing = []
        for part in parts:
            try:
                if os.path.getsize(part) > 0:
                    existing.append(part)
                    continue
            except OSError:
                pass
            # Attempts that never wrote media (e.g. a refused stream URL)
            # leave empty files behind.
            try:
                os.unlink(part)
            except OSError:
                pass

        if not existing:
            return

        if len(existing) == 1:
            # A single attempt produced media, no merge needed. It may still be
            # stored as a part file if an earlier attempt failed.
            if existing[0] != base:
                try:
                    os.replace(existing[0], base)
                except OSError as e:
                    self.logger.warning(e)
            return

        usable = []
        for part in existing:
            if self._isReadablePart(part):
                usable.append(part)
            else:
                self.logger.warning(
                    f'Recording part {os.path.basename(part)} is damaged, keeping it as a separate file')

        if base in existing and base not in usable:
            # Never replace a damaged file that still holds recorded media.
            return
        if len(usable) < 2:
            return

        total_size = sum(os.path.getsize(part) for part in usable)

        # Check available disk space to avoid crashing or corrupting files on low-resource machines
        try:
            free_space = shutil.disk_usage(os.path.dirname(os.path.abspath(base))).free
            if free_space < total_size * 1.05:
                self.logger.warning(
                    f'Insufficient disk space to merge {len(usable)} recording parts '
                    f'(need ~{int(total_size / (1024 * 1024))}MB, have {int(free_space / (1024 * 1024))}MB). '
                    'Keeping parts separate.')
                return
        except Exception as e:
            self.logger.debug(f'Could not check disk space: {e}')

        stem, ext = os.path.splitext(base)
        list_path = stem + '.concat.txt'
        merged_path = stem + '.merged' + ext
        try:
            with open(list_path, 'w', encoding='utf-8') as list_file:
                for part in usable:
                    path = os.path.abspath(part).replace("'", "'\\''")
                    list_file.write(f"file '{path}'\n")

            self.log(f'Merging {len(usable)} recording parts into one file')
            result = subprocess.run(
                [FFMPEG_PATH, '-hide_banner', '-loglevel', 'error',
                 '-f', 'concat', '-safe', '0', '-i', list_path,
                 '-c', 'copy', '-fflags', '+genpts', '-avoid_negative_ts', 'make_zero',
                 '-y', merged_path],
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            merged_size = os.path.getsize(merged_path) if os.path.exists(merged_path) else 0
            # The concat demuxer reports success even when it stops at a part
            # it cannot read, so a much smaller result means a partial merge.
            # Using 0.70 ratio accommodates overlapping live stream segments.
            if result.returncode == 0 and merged_size >= total_size * 0.70:
                os.replace(merged_path, base)
                for part in usable:
                    if part != base:
                        try:
                            os.unlink(part)
                        except OSError:
                            pass
            else:
                output = result.stderr.decode('utf-8', 'replace').strip().splitlines()
                self.logger.error(
                    'Could not merge recording parts, keeping them separate: '
                    + (output[-1] if output else 'unknown error'))
        except Exception as e:
            self.logger.exception(e)
        finally:
            for path in (list_path, merged_path):
                if os.path.exists(path):
                    try:
                        os.unlink(path)
                    except OSError:
                        pass

    # Recording file naming used by the downloaders, plus the part suffix
    # applied by nextRecordingFilename().
    _PART_PATTERN = re.compile(r'^(?P<stem>.+)\.part(?P<number>\d+)(?P<ext>\.[^.]+)$')
    # Raw MPEG-TS the HLS downloader keeps until ffmpeg remuxes it.
    _TEMP_SUFFIX = '.tmp.ts'

    def _orphanedPartGroups(self, folder):
        """Group leftover ``<show>.partN.<ext>`` files by their target file.

        Returns ``{base_path: [part_paths]}`` with the base recording first
        (when it exists) and the parts in ascending part number.
        """
        groups = {}
        try:
            entries = list(os.scandir(folder))
        except OSError:
            return groups
        for entry in entries:
            match = self._PART_PATTERN.match(entry.name)
            if not match or not entry.is_file():
                continue
            base = os.path.join(folder, match.group('stem') + match.group('ext'))
            groups.setdefault(base, []).append(
                (int(match.group('number')), entry.path))
        result = {}
        for base, numbered in groups.items():
            parts = []
            if os.path.isfile(base):
                parts.append(base)
            parts.extend(path for _, path in sorted(numbered))
            result[base] = parts
        return result

    def _hasSegmentFiles(self, path):
        """True when ffmpeg already wrote ``<stem>_NNN.<ext>`` segments."""
        folder, name = os.path.split(path)
        stem = os.path.splitext(name)[0] + '_'
        ext = os.path.splitext(name)[1]
        try:
            entries = os.scandir(folder)
        except OSError:
            return False
        with entries as iterator:
            for entry in iterator:
                if entry.name.startswith(stem) and entry.name.endswith(ext):
                    return True
        return False

    def _recoverTempRecording(self, temp_path):
        """Remux a native HLS download that was never turned into a video.

        ``getVideoNativeHLS`` keeps raw MPEG-TS in ``<show>.tmp.ts`` until
        ffmpeg remuxes it. A kill during the download leaves the file behind
        and the recorded bytes would otherwise never be playable.
        """
        target = temp_path[:-len(self._TEMP_SUFFIX)] + '.' + CONTAINER
        if self._hasSegmentFiles(target):
            # SEGMENT_TIME splits the show into separate segment files; the
            # temp file is only the source for ffmpeg and does not belong in
            # the folder as an extra full recording.
            self.log(f'Keeping {os.path.basename(temp_path)}, '
                     'the show was already split into segment files')
            return False
        try:
            temp_size = os.path.getsize(temp_path)
        except OSError:
            return False
        if temp_size == 0:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            return False
        try:
            target_size = os.path.getsize(target)
        except OSError:
            target_size = 0
        if target_size >= temp_size:
            # A finished remux keeps the larger, playable file.
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            return True

        result = subprocess.run(
            [FFMPEG_PATH, '-hide_banner', '-loglevel', 'error', '-y',
             '-i', temp_path, '-c', 'copy', target],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        if result.returncode != 0 or not os.path.exists(target) or os.path.getsize(target) == 0:
            output = result.stderr.decode('utf-8', 'replace').strip().splitlines()
            self.logger.warning(
                f'Could not recover {os.path.basename(temp_path)}, keeping it: '
                + (output[-1] if output else 'unknown error'))
            return False
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        self.log(f'Recovered {os.path.basename(target)} from an interrupted download')
        return True

    def recoverOrphanedRecordings(self):
        """Finish recordings a previous process left behind.

        ``recording_base`` and ``recording_parts`` only live in memory, so a
        crash or container restart strands part files and raw HLS temp files
        in the download folder. Called once when the bot thread starts.
        """
        if getattr(self, '_recoveredRecordings', False):
            return
        self._recoveredRecordings = True
        folder = self.outputFolder
        if not os.path.isdir(folder):
            return

        try:
            for entry in list(os.scandir(folder)):
                if not entry.is_file():
                    continue
                if entry.name.endswith(self._TEMP_SUFFIX):
                    try:
                        self._recoverTempRecording(entry.path)
                    except Exception as e:
                        self.logger.exception(e)
                elif os.path.splitext(entry.name)[0].endswith('.merged') \
                        or entry.name.endswith('.concat.txt'):
                    # Left over from a merge that was killed. The parts are
                    # still there, so the merge below rebuilds it.
                    try:
                        os.unlink(entry.path)
                    except OSError:
                        pass
        except OSError as e:
            self.logger.warning(e)
            return

        for base, parts in self._orphanedPartGroups(folder).items():
            try:
                self._consolidateParts(base, parts)
            except Exception as e:
                self.logger.exception(e)
        try:
            self.cache_file_list()
        except Exception as e:
            self.logger.exception(e)

    def _sleep(self, time):
        while time > 0:
            sleep(1)
            time -= 1
            if self.quitting or not self.running:
                return
            if self.bulk_update and self.sc in (Status.PUBLIC, Status.PRIVATE):
                return

    def run(self):
        while not self.quitting:
            while not self.running and not self.quitting:
                sleep(1)
            if self.quitting:
                break

            try:
                self.recoverOrphanedRecordings()
            except Exception as e:
                self.logger.exception(e)

            offline_time = self.long_offline_timeout + 1  # Don't start polling when streamer was offline at start
            while self.running:
                try:
                    self.recording = False
                    if not self.bulk_update or self.sc == Status.NOTRUNNING:
                        try:
                            self.sc = self.getStatus()
                        except Exception as e:
                            self.logger.exception(e)
                            self.sc = Status.ERROR
                    # Check if the status has changed and log the update if it's different from the previous status
                    if self.sc != self.previous_status:
                        self.log(self.status())
                        self.previous_status = self.sc
                    # The show is over when the streamer is no longer online.
                    # Errors while a show is running only interrupt the stream,
                    # so keep the recording open and resume it later.
                    if self.reconcileRecordingConnection(self.sc):
                        try:
                            self.finalizeRecording()
                            self.cache_file_list()
                        except Exception as e:
                            self.logger.exception(e)
                    if self.sc == Status.ERROR:
                        self._sleep(self.sleep_on_error)
                    if self.sc == Status.OFFLINE:
                        offline_time += self.sleep_on_offline
                        if offline_time > self.long_offline_timeout:
                            self.sc = Status.LONG_OFFLINE
                    elif self.sc == Status.PUBLIC or self.sc == Status.PRIVATE:
                        offline_time = 0
                        if self.sc == Status.PUBLIC:
                            if self.cookie_update_interval > 0 and self.cookieUpdater is not None:
                                def update_cookie():
                                    while self.sc == Status.PUBLIC and not self.quitting and self.running:
                                        self._sleep(self.cookie_update_interval)
                                        ret2 = self.cookieUpdater()
                                        if ret2:
                                            self.debug('Updated cookies')
                                        else:
                                            self.logger.warning('Failed to update cookies')
                                cookie_update_process = Thread(target=update_cookie)
                                cookie_update_process.start()

                            try:
                                video_url = self.getVideoUrl()
                            except Exception as e:
                                self.logger.exception(e)
                                self.logger.error('Failed to get video url')
                                video_url = None
                            if video_url is None:
                                self.sc = Status.ERROR
                                self.logger.error(self.status())
                                self._sleep(max(self.sleep_on_error, 20))
                                continue
                            self.log('Started downloading show')
                            self.recording = True
                            file = self.nextRecordingFilename()
                            started = time.monotonic()
                            try:
                                ret = self.getVideo(self, video_url, file)
                            except Exception as e:
                                self.logger.exception(e)
                                ret = False
                            if not ret:
                                self.log('Recording ended with error')
                                self.recording = False
                                self.sc = Status.ERROR
                                self.log(self.status())
                                # A working recording that got interrupted is
                                # resumed quickly; a stream that fails right
                                # away keeps the full error delay.
                                if time.monotonic() - started >= 60:
                                    self._sleep(min(self.sleep_on_error, 5))
                                else:
                                    self._sleep(self.sleep_on_error)
                                continue
                            self.recording = False
                            self.log('Recording ended')
                            try:
                                self.cache_file_list()
                            except Exception as e:
                                self.logger.exception(e)
                except Exception as e:
                    self.logger.exception(e)
                    try:
                        self.cache_file_list()
                    except Exception as e:
                        self.logger.exception(e)
                    self.log(self.status())
                    self.recording = False
                    self._sleep(self.sleep_on_error)
                    continue

                if self.quitting:
                    break
                elif self.bulk_update:
                    self._sleep(3)
                elif self.ratelimit:
                    self._sleep(self.sleep_on_ratelimit)
                elif offline_time > self.long_offline_timeout:
                    self._sleep(self.sleep_on_long_offline)
                elif self.sc == Status.PRIVATE:
                    self._sleep(self.sleep_on_private)
                else:
                    self._sleep(self.sleep_on_offline)

            self.sc = Status.NOTRUNNING
            self.log("Stopped")
            try:
                self.finalizeRecording()
                self.cache_file_list()
            except Exception as e:
                self.logger.exception(e)

    def setStatus(self, sc):
        if self.sc == Status.LONG_OFFLINE and sc == Status.OFFLINE:
            return
        self.sc = sc

    def getPlaylistVariants(self, url=None, m3u_data=None):
        sources = []

        if isinstance(m3u_data, m3u8.M3U8):
            variant_m3u8 = m3u_data
        elif isinstance(m3u_data, str):
            variant_m3u8 = m3u8.loads(m3u_data)
        elif not m3u_data or url:
            result = self.session.get(
                url,
                headers=self.headers,
                cookies=self.cookies,
                timeout=10,
            )
            status_code = getattr(result, 'status_code', 200)
            if status_code != 200:
                self.logger.warning(
                    "Could not fetch HLS master playlist %s (HTTP %s)",
                    url,
                    status_code,
                )
                return None
            m3u8_doc = getattr(result, 'text', None)
            if not m3u8_doc:
                content = getattr(result, 'content', b'')
                m3u8_doc = content.decode("utf-8") if isinstance(content, bytes) else str(content)
            variant_m3u8 = m3u8.loads(m3u8_doc)
        else:
            return sources

        if getattr(self, 'siteslug', None) in {'MFC', 'CB', 'CS', 'FL', 'SC'}:
            if isinstance(m3u_data, str):
                health_content = m3u_data
                health_url = url or '<m3u-data>'
            elif isinstance(m3u_data, m3u8.M3U8):
                health_content = m3u_data.dumps()
                health_url = url or '<m3u8-object>'
            else:
                health_content = m3u8_doc
                health_url = url or '<unknown>'
            inspect_and_report(
                self.logger,
                self.siteslug,
                health_url,
                health_content,
            )

        for playlist in variant_m3u8.playlists:
            stream_info = playlist.stream_info
            resolution = stream_info.resolution if type(stream_info.resolution) is tuple else (0, 0)
            sources.append({
                'url': playlist.uri,
                'resolution': resolution,
                'frame_rate': stream_info.frame_rate,
                'bandwidth': stream_info.bandwidth
            })

        if not variant_m3u8.is_variant and len(sources) >= 1:
            self.logger.warn("Not variant playlist, can't select resolution")
            return None
        return sources  # [(url, (width, height)),...]

    def _selectSource(self, sources):
        if not sources:
            self.logger.error("No available sources")
            return None

        for source in sources:
            width, height = source['resolution']
            if width < height:
                source['resolution_diff'] = width - WANTED_RESOLUTION
            else:
                source['resolution_diff'] = height - WANTED_RESOLUTION

        sources.sort(key=lambda a: abs(a['resolution_diff']))
        selected_source = None

        if WANTED_RESOLUTION_PREFERENCE == 'exact':
            if sources[0]['resolution_diff'] == 0:
                selected_source = sources[0]
        elif WANTED_RESOLUTION_PREFERENCE == 'closest' or len(sources) == 1:
            selected_source = sources[0]
        elif WANTED_RESOLUTION_PREFERENCE == 'exact_or_least_higher':
            for source in sources:
                if source['resolution_diff'] >= 0:
                    selected_source = source
                    break
        elif WANTED_RESOLUTION_PREFERENCE == 'exact_or_highest_lower':
            for source in sources:
                if source['resolution_diff'] <= 0:
                    selected_source = source
                    break
        else:
            self.logger.error('Invalid value for WANTED_RESOLUTION_PREFERENCE')
            return None

        if selected_source is None:
            self.logger.error("Couldn't select a resolution")
        return selected_source

    def getWantedResolutionPlaylist(self, url):
        try:
            sources = self.getPlaylistVariants(url)
            if sources is None:
                return None

            selected_source = self._selectSource(sources)
            if selected_source is None:
                return None

            if selected_source['resolution'][1] != 0:
                frame_rate = ''
                if selected_source['frame_rate'] is not None and selected_source['frame_rate'] != 0:
                    frame_rate = f" {selected_source['frame_rate']}fps"
                self.logger.info(f"Selected {selected_source['resolution'][0]}x{selected_source['resolution'][1]}{frame_rate} resolution")
            selected_source_url = selected_source['url']
            selected_url = urljoin(url, selected_source_url)
            if not self.validateRecordingPlaylist(selected_url):
                return None
            return selected_url
        except BaseException as e:
            self.logger.error("Can't get playlist, got some error: " + str(e))
            traceback.print_tb(e.__traceback__)
            return None

    def validateRecordingPlaylist(self, url):
        """Make sure a resolved HLS URL is usable before starting FFmpeg."""
        if isinstance(url, os.PathLike):
            return True
        if not url or '.m3u8' not in str(url).lower():
            return True
        if getattr(self, 'siteslug', None) == 'SC':
            return True

        try:
            result = self.session.get(
                url,
                headers=self.headers,
                cookies=self.cookies,
                timeout=5,
            )
            status_code = getattr(result, 'status_code', 200)
            if status_code != 200:
                self.logger.warning(
                    "Selected HLS playlist is unavailable (HTTP %s): %s",
                    status_code,
                    url,
                )
                return False

            content = getattr(result, 'text', None)
            if not content:
                raw_content = getattr(result, 'content', b'')
                content = (
                    raw_content.decode("utf-8")
                    if isinstance(raw_content, bytes)
                    else str(raw_content)
                )
            health = inspect_playlist(content, str(url))
            if health.is_variant:
                return True
            return health.segment_count > 0
        except Exception as error:
            self.logger.warning(
                "Could not validate selected HLS playlist (%s): %s",
                url,
                error,
            )
            return False

    def getVideoUrl(self):
        pass

    def progressInfo(self, p):
        if p['status'] == 'downloading':
            self.log("Downloading " + str(round(float(p['downloaded_bytes']) / float(p['total_bytes']) * 100, 1)) + "%")
        if p['status'] == 'finished':
            self.log("Show ended. File:" + p['filename'])

    @property
    def outputFolder(self):
        base = DOWNLOADS_DIR
        if DOWNLOADS_BY_DATE:
            date_folder = getattr(self, '_download_date_folder', None)
            if not date_folder:
                date_folder = datetime.now().strftime(
                    DOWNLOAD_DATE_FORMAT
                )
                self._download_date_folder = date_folder
            base = os.path.join(base, date_folder)
        return str(os.path.join(base, self.username + ' [' + self.siteslug + ']'))

    def genOutFilename(self, create_dir=True):
        folder = self.outputFolder
        if create_dir:
            os.makedirs(folder, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        stem = os.path.join(folder, f'{self.username}-{timestamp}')
        filename = stem + '.' + CONTAINER
        sequence = 1
        while os.path.exists(filename):
            filename = f'{stem}.{sequence}.{CONTAINER}'
            sequence += 1
        return filename

    @classmethod
    def fromConfig(cls, data):
        instance = cls(username=data['username'])
        instance.running = data.get('running', True)
        instance.country = data.get('country')
        instance.gender = data.get('gender')
        return instance

    def export(self):
        return {
            "site": self.site,
            "username": self.username,
            "running": self.running,
            "country": self.country,
            "gender": self.gender.value if isinstance(self.gender, Enum) else self.gender,
        }

    @staticmethod
    def str2site(site: str):
        site = site.lower()
        for sitecls in LOADED_SITES:
            if site == sitecls.site.lower() or \
                    site == sitecls.siteslug.lower() or \
                    site in sitecls.aliases:
                return sitecls
        return None

    @staticmethod
    def createInstance(username: str, site: str = None):
        if site:
            site_cls = Bot.str2site(site)
            if site_cls:
                return site_cls(username)
            else:
                raise Exception('No such site')
        return None


class RoomIdBot(Bot):
    def __init__(self, username, room_id=None):
        self.room_id = None
        super().__init__(username)

        if room_id and username:
            self.room_id = room_id

        if self.room_id is None and username.isnumeric():  # Username might be the room ID
            username_real = self.getUsernameFromRoomId(username)
            if username_real is not None:  # Username might not be the room ID even though it is numeric
                self.logger.debug(f'Found username: {username_real}')
                self.room_id = username
                self.setUsername(username_real)

        if self.room_id is None:  # We need to get the room ID
            self.room_id = self.getRoomIdFromUsername(username)
            if self.room_id:
                self.logger.debug(f'Found room ID: {self.room_id}')

        if self.room_id is None:  # Still no room ID, streamer probably does not exist
            self.logger.warning(f'Room ID not found')
            self.sc = Status.NOTEXIST

        self.logger = self.getLogger()
        self.url = self.getWebsiteURL()

    @classmethod
    def fromConfig(cls, data):
        instance = cls(username=data['username'], room_id=data.get('room_id'))
        instance.running = data.get('running', True)
        return instance

    def export(self):
        data = super().export()
        data['room_id'] = self.room_id
        return data

    def getRoomIdFromUsername(self, username):
        return None

    def getUsernameFromRoomId(self, room_id):
        return None
