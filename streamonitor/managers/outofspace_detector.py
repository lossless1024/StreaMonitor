import os.path
import shutil
from time import sleep
import streamonitor.log as log
from threading import Thread
from parameters import DOWNLOADS_DIR, MIN_FREE_DISK_PERCENT
from streamonitor.clean_exit import CleanExit


class OOSDetector(Thread):
    under_threshold_message = 'Free space is under threshold. Exiting.'

    def __init__(self, streamers):
        super().__init__()
        self.streamers = streamers
        self.daemon = True
        self.logger = log.Logger("out_of_space_detector")

    @staticmethod
    def free_space():
        if os.path.exists(DOWNLOADS_DIR):
            usage = shutil.disk_usage(DOWNLOADS_DIR)
        else:
            usage = shutil.disk_usage('.')
        free_percent = usage.free / usage.total * 100
        return free_percent

    @staticmethod
    def disk_space_good():
        return OOSDetector.free_space() > MIN_FREE_DISK_PERCENT

    def run(self):
        while True:
            if not self.disk_space_good():
                self.logger.warning(self.under_threshold_message)
                CleanExit(self.streamers)()
                return
            sleep(5)
