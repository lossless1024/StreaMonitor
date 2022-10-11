from __future__ import unicode_literals
import os
from enum import Enum
from time import sleep
from datetime import datetime
from threading import Thread

import requests

import streamonitor.log as log
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
        Status.NOTRUNNING: "Not running"
    }

    def __init__(self, username):
        super().__init__()
        self.username = username
        self.logger = log.Logger("[" + self.siteslug + "] " + self.username).get_logger()

        self.lastInfo = {}  # This dict will hold information about stream after getStatus is called. One can use this in getVideoUrl
        self.running = False
        self.sc = self.Status.NOTRUNNING  # Status code
        self.getVideo = getVideoFfmpeg
        self.stopDownload = None

    def stop(self, a, b):
        if self.running:
            self.log("Stopping...")
            if self.stopDownload:
                self.stopDownload()
            self.running = False

    def getStatus(self):
        return self.Status.UNKNOWN

    def log(self, message):
        self.logger.info(message)

    def status(self):
        message = self.status_messages.get(self.sc) or "Unknown error"
        if self.sc == self.Status.NOTEXIST:
            self.running = False
        return message

    def run(self):
        self.running = True
        offline_time = self.long_offline_timeout + 1  # Don't start polling when streamer was offline at start
        while self.running:
            try:
                self.sc = self.getStatus()
                self.log(self.status())
                if self.sc == self.Status.ERROR:
                    sleep(self.sleep_on_error)
                if self.sc == self.Status.OFFLINE:
                    offline_time += self.sleep_on_offline
                    if offline_time > self.long_offline_timeout:
                        self.sc = self.Status.LONG_OFFLINE
                elif self.sc == self.Status.PUBLIC or self.sc == self.Status.PRIVATE:
                    offline_time = 0
                    if self.sc == self.Status.PUBLIC:
                        self.log('Started downloading show')
                        self.getVideo(self, self.getVideoUrl(), self.genOutFilename())
            except Exception as e:
                self.logger.exception(e)
                self.log(self.status())
                sleep(self.sleep_on_error)
                continue

            if self.ratelimit:
                sleep(self.sleep_on_ratelimit)
            elif offline_time > self.long_offline_timeout:
                sleep(self.sleep_on_long_offline)
            else:
                sleep(self.sleep_on_offline)
        self.sc = self.Status.NOTRUNNING
        self.log("Stopped")

    def getBestSubPlaylist(self, url, position=0):  # Default is the first, set -1 to last
        try:
            r = requests.get(url)
            best = [file for file in r.content.split(b'\n') if b'm3u8' in file][position].decode('utf-8')
            return '/'.join(url.split('.m3u8')[0].split('/')[:-1]) + '/' + best
        except:
            return None

    def getVideoUrl(self):
        pass

    def progressInfo(self, p):
        if p['status'] == 'downloading':
            self.log("Downloading " + str(round(float(p['downloaded_bytes']) / float(p['total_bytes']) * 100, 1)) + "%")
        if p['status'] == 'finished':
            self.log("Show ended. File:" + p['filename'])

    def genOutFilename(self, create_dir=True):
        folder = 'downloads/' + self.username + ' [' + self.siteslug + ']'
        if create_dir:
            os.makedirs(folder, exist_ok=True)
        now = datetime.now()
        filename = folder + '/' + self.username + '-' + str(now.strftime("%Y%m%d-%H%M%S")) + '.mp4'
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
