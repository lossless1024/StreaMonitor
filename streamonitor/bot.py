from __future__ import unicode_literals
import os
import traceback

import m3u8
from enum import Enum
from time import sleep
from datetime import datetime
from threading import Thread

import requests
import requests.cookies

import streamonitor.log as log
from parameters import DOWNLOADS_DIR, DEBUG, WANTED_RESOLUTION, WANTED_RESOLUTION_PREFERENCE, CONTAINER, HTTP_USER_AGENT


class Bot(Thread):
    loaded_sites = set()
    username = None
    site = None
    siteslug = None
    aliases = []
    ratelimit = False

    sleep_on_private = 5
    sleep_on_offline = 5
    sleep_on_long_offline = 300
    sleep_on_error = 20
    sleep_on_ratelimit = 180
    long_offline_timeout = 600

    headers = {
        "User-Agent": HTTP_USER_AGENT
    }

    class Status(Enum):
        UNKNOWN = 1
        NOTRUNNING = 2
        ERROR = 3
        RESTRICTED = 1403
        PUBLIC = 200
        NOTEXIST = 400
        PRIVATE = 403
        OFFLINE = 404
        LONG_OFFLINE = 410
        RATELIMIT = 429

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

    frame_format_map = {
        'FISHEYE': 'F',
        'PANORAMIC': 'P',
        'CIRCULAR': 'C',
    }

    def __init__(self, username):
        super().__init__()
        self.username = username
        self.logger = self.getLogger()

        self.cookies = None
        self.cookieUpdater = None
        self.cookie_update_interval = 0

        self.lastInfo = {}  # This dict will hold information about stream after getStatus is called. One can use this in getVideoUrl
        self.running = False
        self.quitting = False
        self.sc = self.Status.NOTRUNNING  # Status code
        from streamonitor.downloaders.ffmpeg import getVideoFfmpeg
        self.getVideo = getVideoFfmpeg
        self.stopDownload = None

    def getLogger(self):
        return log.Logger("[" + self.siteslug + "] " + self.username).get_logger()

    def restart(self):
        self.running = True

    def getWebsiteURL(self):
        return ""

    def stop(self, a, b, thread_too=False):
        if self.running:
            self.log("Stopping...")
            if self.stopDownload:
                self.stopDownload()
            self.running = False
        if thread_too:
            self.quitting = True

    def getStatus(self):
        return self.Status.UNKNOWN

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
        message = self.status_messages.get(self.sc) or self.status_messages.get(self.Status.UNKNOWN)
        if self.sc == self.Status.NOTEXIST:
            self.running = False
        return message

    def _sleep(self, time):
        while time > 0:
            sleep(1)
            time -= 1
            if self.quitting:
                return

    def run(self):
        while not self.quitting:
            while not self.running and not self.quitting:
                sleep(1)
            if self.quitting:
                break

            offline_time = self.long_offline_timeout + 1  # Don't start polling when streamer was offline at start
            while self.running:
                try:
                    self.sc = self.getStatus()
                    self.log(self.status())
                    if self.sc == self.Status.ERROR:
                        self._sleep(self.sleep_on_error)
                    if self.sc == self.Status.OFFLINE:
                        offline_time += self.sleep_on_offline
                        if offline_time > self.long_offline_timeout:
                            self.sc = self.Status.LONG_OFFLINE
                    elif self.sc == self.Status.PUBLIC or self.sc == self.Status.PRIVATE:
                        offline_time = 0
                        if self.sc == self.Status.PUBLIC:
                            if self.cookie_update_interval > 0 and self.cookieUpdater is not None:
                                def update_cookie():
                                    while self.sc == self.Status.PUBLIC and not self.quitting and self.running:
                                        self._sleep(self.cookie_update_interval)
                                        ret = self.cookieUpdater()
                                        if ret:
                                            self.debug('Updated cookies')
                                        else:
                                            self.logger.warning('Failed to update cookies')
                                cookie_update_process = Thread(target=update_cookie)
                                cookie_update_process.start()

                            video_url = self.getVideoUrl()
                            if video_url is None:
                                self.sc = self.Status.ERROR
                                self.logger.error(self.status())
                                self._sleep(self.sleep_on_error)
                                continue
                            self.log('Started downloading show')
                            os.makedirs(self.outputFolder, exist_ok=True)
                            ret = self.getVideo(self)
                            if not ret:
                                self.sc = self.Status.ERROR
                                self.log(self.status())
                                self._sleep(self.sleep_on_error)
                                continue
                            self.log('Recording ended')
                except Exception as e:
                    self.logger.exception(e)
                    self.log(self.status())
                    self._sleep(self.sleep_on_error)
                    continue

                if self.quitting:
                    break
                elif self.ratelimit:
                    self._sleep(self.sleep_on_ratelimit)
                elif offline_time > self.long_offline_timeout:
                    self._sleep(self.sleep_on_long_offline)
                elif self.sc == self.Status.PRIVATE:
                    self._sleep(self.sleep_on_private)
                else:
                    self._sleep(self.sleep_on_offline)

            self.sc = self.Status.NOTRUNNING
            self.log("Stopped")

    def getPlaylistVariants(self, url):
        sources = []
        result = requests.get(url, headers=self.headers, cookies=self.cookies)
        m3u8_doc = result.content.decode("utf-8")
        variant_m3u8 = m3u8.loads(m3u8_doc)
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
        return sources #  [(url, (width, height)),...]

    def getWantedResolutionPlaylist(self, url):
        try:
            sources = self.getPlaylistVariants(url)
            if sources is None:
                return None

            if len(sources) == 0:
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
                return None

            if selected_source['resolution'][1] != 0:
                frame_rate = ''
                if selected_source['frame_rate'] is not None and selected_source['frame_rate'] != 0:
                    frame_rate = f" {selected_source['frame_rate']}fps"
                self.logger.info(f"Selected {selected_source['resolution'][0]}x{selected_source['resolution'][1]}{frame_rate} resolution")
            selected_source_url = selected_source['url']
            if selected_source_url.startswith("https://"):
                return selected_source_url
            else:
                return '/'.join(url.split('.m3u8')[0].split('/')[:-1]) + '/' + selected_source_url
        except BaseException as e:
            self.logger.error("Can't get playlist, got some error: " + str(e))
            traceback.print_tb(e.__traceback__)
            return None

    def getVideoUrl(self):
        pass

    def progressInfo(self, p):
        if p['status'] == 'downloading':
            self.log("Downloading " + str(round(float(p['downloaded_bytes']) / float(p['total_bytes']) * 100, 1)) + "%")
        if p['status'] == 'finished':
            self.log("Show ended. File:" + p['filename'])

    @property
    def outputFolder(self):
        return os.path.join(DOWNLOADS_DIR, self.username + ' [' + self.siteslug + ']')

    def export(self):
        return {"site": self.site, "username": self.username, "running": self.running}

    @staticmethod
    def str2site(site: str):
        site = site.lower()
        for sitecls in Bot.loaded_sites:
            if site == sitecls.site.lower() or \
                    site == sitecls.siteslug.lower() or \
                    site in sitecls.aliases:
                return sitecls

    @staticmethod
    def createInstance(username: str, site: str = None):
        if site:
            return Bot.str2site(site)(username)

    def vrFilenamePart(self):
        return ""

    def filename(self):
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        return os.path.join(self.outputFolder, f'{self.username}{self.vrFilenamePart()}-{timestamp}.{CONTAINER}')

    def filenameSegmented(self):
        return os.path.join(self.outputFolder, f'{self.username}{self.vrFilenamePart()}-%Y%m%d-%H%M%S.{CONTAINER}')
