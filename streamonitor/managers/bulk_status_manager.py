from time import sleep

import requests

from streamonitor.bot import LOADED_SITES
from streamonitor.manager import Manager
from streamonitor.clean_exit import CleanExit
import streamonitor.log as log


class BulkStatusManager(Manager):
    def __init__(self, streamers):
        super().__init__(streamers)
        self.logger = log.Logger("bulk_status_manager")

    def run(self):
        bulk_bots = frozenset([site for site in LOADED_SITES if hasattr(site, 'getStatusBulk') and site.bulk_update])
        bot_sessions = {}

        for bot in bulk_bots:
            bot_sessions[bot] = requests.Session()

        while True:
            bot_bulk = {}
            for streamer in self.streamers:
                bot_class = streamer.__class__
                if bot_class not in bulk_bots:
                    continue
                if not streamer.running:
                    continue
                bot_bulk.setdefault(bot_class, set()).add(streamer)
            for bot_class, streamers in bot_bulk.items():
                try:
                    self.logger.debug('Get ' + str(bot_class.site) + ' bulk status')
                    bot_class.getStatusBulk(streamers)
                except Exception as e:
                    self.logger.error(f"Error in bulk status check for {bot_class.site}: {e}")
            sleep(3)

    def do_quit(self, _=None, __=None, ___=None):
        CleanExit(self.streamers)()
