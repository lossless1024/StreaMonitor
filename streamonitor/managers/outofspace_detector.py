import shutil
from time import sleep
import streamonitor.log as log
from streamonitor.manager import Manager
from parameters import DOWNLOADS_DIR, MIN_FREE_DISK_PERCENT
from streamonitor.clean_exit import CleanExit


class OOSDetector(Manager):
    under_threshold_message = 'Free space is under threshold. Exiting.'

    def __init__(self, streamers):
        super().__init__(streamers)
        self.daemon = True
        self.logger = log.Logger("out_of_space_detector")

    @staticmethod
    def disk_space_good():
        usage = shutil.disk_usage(DOWNLOADS_DIR)
        free_percent = usage.free / usage.total * 100
        return free_percent > MIN_FREE_DISK_PERCENT

    def run(self):
        while True:
            if not self.disk_space_good():
                self.logger.warning(self.under_threshold_message)
                CleanExit(self.streamers)()
                return
            sleep(5)
