from __future__ import unicode_literals
import os
import m3u8
from enum import Enum
from time import sleep
from datetime import datetime
from threading import Thread

import requests
import requests.cookies

import streamonitor.log as log
from parameters import DOWNLOADS_DIR, DEBUG, WANTED_RESOLUTION, WANTED_RESOLUTION_PREFERENCE
from streamonitor.downloaders.ffmpeg import getVideoFfmpeg


class Bot(Thread):
    loaded_sites = set()
    username = None
    site = None
    siteslug = None
    aliases = []
    ratelimit = False

    sleep_on_offline = 2
    sleep_on_long_offline = 300
    sleep_on_error = 20
    sleep_on_ratelimit = 180
    long_offline_timeout = 600

    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:75.0) Gecko/20100101 Firefox/75.0"
    }

    class Status(Enum):
        UNKNOWN = 1
        NOTRUNNING = 2
        ERROR = 3
        PUBLIC = 200
        NOTEXIST = 400
        PRIVATE = 403
        OFFLINE = 404
        LONG_OFFLINE = 410
        RATELIMIT = 429

    status_messages = {
        Status.PUBLIC: "Channel online",
        Status.OFFLINE: "No stream",
        Status.LONG_OFFLINE: "No stream for a while",
        Status.PRIVATE: "Private show",
        Status.RATELIMIT: "Rate limited",
        Status.NOTEXIST: "Nonexistent user",
        Status.NOTRUNNING: "Not running",
        Status.ERROR: "Error on downloading"
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
        self.getVideo = getVideoFfmpeg
        self.stopDownload = None

    def getLogger(self):
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
        message = self.status_messages.get(self.sc) or "Unknown error"
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
                            ret = self.getVideo(self, video_url, self.genOutFilename())
                            if not ret:
                                self.sc = self.Status.ERROR
                                self.log(self.status())
                                self._sleep(self.sleep_on_error)
                                continue
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
            resolution = playlist.stream_info.resolution if type(playlist.stream_info.resolution) is tuple else (0, 0)
            sources.append(( playlist.uri, resolution ))

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

            sources2 = []
            for source in sources:
                width, height = source[1]
                if width < height:
                    source += (width - WANTED_RESOLUTION,)
                else:
                    source += (height - WANTED_RESOLUTION,)
                sources2.append(source)
            sources = sources2

            sources.sort(key=lambda a: abs(a[2]))
            selected_source = None

            if WANTED_RESOLUTION_PREFERENCE == 'exact':
                if sources[0][2] == 0:
                    selected_source = sources[0]
            elif WANTED_RESOLUTION_PREFERENCE == 'closest' or len(sources) == 1:
                selected_source = sources[0]
            elif WANTED_RESOLUTION_PREFERENCE == 'exact_or_least_higher':
                for source in sources:
                    if source[2] >= 0:
                        selected_source = source
                        break
            elif WANTED_RESOLUTION_PREFERENCE == 'exact_or_highest_lower':
                for source in sources:
                    if source[2] <= 0:
                        selected_source = source
                        break
            else:
                self.logger.error('Invalid value for WANTED_RESOLUTION_PREFERENCE')
                return None

            if selected_source is None:
                self.logger.error("Couldn't select a resolution")
                return None

            if selected_source[1][1] != 0:
                self.logger.info(f'Selected {selected_source[1][0]}x{selected_source[1][1]} resolution')
            selected_source_url = selected_source[0]
            if selected_source_url.startswith("https://"):
                return selected_source_url
            else:
                return '/'.join(url.split('.m3u8')[0].split('/')[:-1]) + '/' + selected_source_url
        except BaseException as e:
            self.logger.error("Can't get playlist, got some error: " + str(e))
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

    def genOutFilename(self, create_dir=True):
        folder = self.outputFolder
        if create_dir:
            os.makedirs(folder, exist_ok=True)
        now = datetime.now()
        filename = os.path.join(folder, self.username + '-' + str(now.strftime("%Y%m%d-%H%M%S")) + '.mp4')
        return filename

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
