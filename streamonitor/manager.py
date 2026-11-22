import math
from logging import INFO, WARN, ERROR
from threading import Thread
from termcolor import colored
import terminaltables.terminal_io
from terminaltables import AsciiTable
import streamonitor.config as config
import streamonitor.log as log
from streamonitor.bot import Bot, LOADED_SITES
from streamonitor.clean_exit import CleanExit
from streamonitor.managers.outofspace_detector import OOSDetector

from streamonitor.enums import Status


class Manager(Thread):
    def __init__(self, streamers):
        super().__init__()
        self.daemon = True
        self.streamers = streamers
        self.logger = log.Logger("manager")

    def execCmd(self, line):
        parts = str(line).split(' ')
        if 'do_' + parts[0] not in dir(self):
            return 'Unknown command'

        command = getattr(self, 'do_' + parts[0])
        if command:
            username = parts[1] if len(parts) > 1 else ""
            site = parts[2] if len(parts) > 2 else ""
            streamer = self.getStreamer(username, site)
            return command(streamer, username, site)

    def getStreamer(self, username, site):
        found = None
        site = Bot.str2site(site)
        if site:
            site = site.site
        for streamer in self.streamers:
            if streamer.username == username:
                if site and site != "":
                    if streamer.site == site:
                        return streamer
                else:
                    if not found:
                        found = streamer
                    else:
                        self.logger.error('Multiple users exist with this username, specify site too')
                        return None
        return found

    def saveConfig(self):
        if config.favorites_only:
            return
        config.saveStreamers(self.streamers)

    def do_fav(self, streamer, username, site):
        if username.lower() == "list":
            favorites_config = config.load_favorites_config()
            if favorites_config is None:
                favorites_config = []
            favorites = [
                entry for entry in favorites_config
                if entry.get("favorite") is True
            ]
            if not favorites:
                return "No favorite models"
            return "\n".join(
                f"{entry['site']}/{entry['username']}" for entry in favorites
            )
        if not username:
            return "Missing username"

        matches = config.sync_favorites_config()
        candidates = []
        for entry in matches:
            if entry["username"].lower() != username.lower():
                continue
            if site:
                site_class = Bot.str2site(site)
                if not site_class or entry["site"].lower() not in (
                    site_class.site.lower(),
                    site_class.siteslug.lower(),
                    *(alias.lower() for alias in site_class.aliases),
                ):
                    continue
            candidates.append(entry)

        if not candidates:
            return "Streamer not found in config.json"
        if len(candidates) > 1:
            return "Multiple matches, specify site"

        entry = candidates[0]
        if config.set_favorite(entry["username"], entry["site"], True):
            return f"Added favorite [{entry['site']}] {entry['username']}"
        return "Could not save favorite"

    def do_unfav(self, streamer, username, site):
        if not username:
            return "Missing username"

        matches = config.sync_favorites_config()
        candidates = []
        for entry in matches:
            if entry["username"].lower() != username.lower():
                continue
            if site:
                site_class = Bot.str2site(site)
                if not site_class or entry["site"].lower() not in (
                    site_class.site.lower(),
                    site_class.siteslug.lower(),
                    *(alias.lower() for alias in site_class.aliases),
                ):
                    continue
            candidates.append(entry)

        if not candidates:
            return "Streamer not found in config.json"
        if len(candidates) > 1:
            return "Multiple matches, specify site"

        entry = candidates[0]
        if config.set_favorite(entry["username"], entry["site"], False):
            return f"Removed favorite [{entry['site']}] {entry['username']}"
        return "Could not remove favorite"

    def do_add(self, streamer, username, site):
        if streamer:
            return 'Streamer already exists'
        elif username and site:
            try:
                streamer = Bot.createInstance(username, site)
                self.streamers.append(streamer)
                streamer.start()
                streamer.restart()
                self.saveConfig()
                return "Added [" + streamer.siteslug + "] " + streamer.username
            except Exception as e:
                return f"Failed to add: {e}"
        else:
            return "Missing value(s)"

    def do_remove(self, streamer, username, site):
        if not streamer:
            return "Streamer not found"
        try:
            streamer.stop(None, None)
            streamer.logger.handlers = []
            self.streamers.remove(streamer)
            self.saveConfig()
            return "OK"
        except Exception as e:
            self.logger.error(e)
            return "Failed to remove streamer"

    def do_start(self, streamer, username, site):
        if not streamer:
            if username == '*':
                for streamer in self.streamers:
                    if not streamer.is_alive():
                        streamer.start()
                    streamer.restart()
                self.saveConfig()
                return "Started all"
            else:
                return "Streamer not found"
        else:
            try:
                if not streamer.is_alive():
                    streamer.start()
                streamer.restart()
                self.saveConfig()
                return "OK"
            except Exception as e:
                self.logger.error(e)
                return "Failed to start"

    def do_stop(self, streamer, username, site):
        if not streamer:
            if username == '*':
                for streamer in self.streamers:
                    streamer.stop(None, None)
                self.saveConfig()
                return "Stopped all"
            else:
                return "Streamer not found"
        else:
            try:
                streamer.stop(None, None)
                self.saveConfig()
                return "OK"
            except Exception as e:
                self.logger.error(e)
                return "Failed to stop"

    def do_restart(self, streamer, username, site):
        if not streamer:
            return "Streamer not found"
        self.do_stop(streamer, username, site)
        return self.do_start(streamer, username, site)
        
    def do_status(self, streamer, username, site):
        output = [["Username", "Site", "Started", "Status"]]

        def line():
            output.append([streamer.username,
                           streamer.site,
                           streamer.running,
                           streamer.status()])

        if streamer:
            line()
        else:
            for streamer in self.streamers:
                line()
        return "Status:\n" + f'Free space: {str(round(OOSDetector.free_space(), 3))}%\n\n' + AsciiTable(output).table

    def do_status2(self, streamer, username, site):
        maxlen = max([len(s.username) for s in self.streamers] or [0])
        termwidth = terminaltables.terminal_io.terminal_size()[0]
        table_nx = math.floor(termwidth/(maxlen+3))
        output = ''
        output += 'Status:\n'

        for site in LOADED_SITES:
            output += site.site + '\n'
            output += ('+' + '-'*(maxlen+2))*table_nx + '+\n'
            site_name = site.site
            i = 0
            for streamer in self.streamers:
                if streamer.site == site_name:
                    output += '!'
                    status_color = None
                    status = streamer.sc
                    if status == Status.PUBLIC: status_color = 'green'
                    if status == Status.PRIVATE: status_color = 'magenta'
                    if status == Status.ERROR: status_color = 'red'
                    if not streamer.running: status_color = 'grey'
                    output += colored(' ' + streamer.username + ' '*(maxlen-len(streamer.username)) + ' ', status_color)
                    i += 1
                    if i == table_nx:
                        output += '!\n'
                        i = 0
            for r in range(i, table_nx):
                output += '! ' + ' ' * maxlen + ' '
            output += '!\n'
            output += ('+' + '-'*(maxlen+2))*table_nx + '+\n'
            output += '\n'
        return output

    def do_quit(self, _=None, __=None, ___=None):
        CleanExit(self.streamers)()
        return "Quitting..."
