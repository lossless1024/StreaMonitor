import math
from threading import Thread
from termcolor import colored
import terminaltables.terminal_io
from terminaltables import AsciiTable
import streamonitor.config as config
import streamonitor.log as log
from streamonitor.bot import Bot


class Manager(Thread):
    def __init__(self, streamers, mode, socket=None):
        super().__init__()
        if mode not in ['console', 'zmq']:
            raise
        self.streamers = streamers
        self.mode = mode
        self.socket = socket
        self.logger = log.Logger("manager_" + mode)

    def getStreamer(self, username, site):
        found = None
        site = Bot.str2site(site)
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

    def reply(self, msg):
        if self.mode == "zmq":
            self.socket.send_string(msg)
        if self.mode == "console":
            self.logger.info(msg)

    def run(self):
        logger = log.Logger("Manager")
        while True:
            line = None
            if self.mode == "zmq":
                line = self.socket.recv_string()
                logger.info("[ZMQ] " + line)
            if self.mode == "console":
                line = input("> ")
            parts = str(line).split(' ')
            command = parts[0]
            username = parts[1] if len(parts) > 1 else ""
            site = parts[2] if len(parts) > 2 else ""
            streamer = self.getStreamer(username, site)

            if command == 'add':
                if streamer:
                    self.reply('Streamer already exists')
                elif username and site:
                    try:
                        streamer = Bot.createInstance(username, site)
                        self.streamers.append(streamer)
                        streamer.start()
                        streamer.restart()
                        self.reply("Added [" + streamer.siteslug + "] " + streamer.username)
                    except:
                        self.reply("Failed to add")
                else:
                    self.reply("Missing value(s)")

            elif command == 'remove':
                if not streamer:
                    self.reply("Streamer not found")
                else:
                    try:
                        streamer.stop(None, None)
                        streamer.logger.handlers = []
                        self.streamers.remove(streamer)
                        self.reply("OK")
                    except Exception as e:
                        logger.error(e)
                        self.reply("Failed to remove streamer")

            elif command == 'start':
                if not streamer:
                    self.reply("Streamer not found")
                else:
                    try:
                        if not streamer.is_alive():
                            streamer.start()
                        streamer.restart()
                        self.reply("OK")
                    except Exception as e:
                        logger.error(e)
                        self.reply("Failed to start")

            elif command == 'stop':
                if not streamer:
                    self.reply("Streamer not found")
                else:
                    try:
                        streamer.stop(None, None)
                        self.reply("OK")
                    except Exception as e:
                        logger.error(e)
                        self.reply("Failed to stop")

            elif command == 'status':
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
                self.reply("Status:\n" + AsciiTable(output).table)

            elif command == 'status2':
                maxlen = max([len(s.username) for s in self.streamers])
                termwidth = terminaltables.terminal_io.terminal_size()[0]
                table_nx = math.floor(termwidth/(maxlen+3))
                output = ''
                output += 'Status:\n'

                for site in Bot.loaded_sites:
                    output += site.site + '\n'
                    output += ('+' + '-'*(maxlen+2))*table_nx + '+\n'
                    site_name = site.site
                    i = 0
                    for streamer in self.streamers:
                        if streamer.site == site_name:
                            output += '!'
                            status_color = None
                            status = streamer.sc
                            if status == Bot.Status.PUBLIC: status_color = 'green'
                            if status == Bot.Status.PRIVATE: status_color = 'magenta'
                            if status == Bot.Status.ERROR: status_color = 'red'
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
                self.reply(output)

            else:
                self.reply('Unknown command')

            config.save_config([s.export() for s in self.streamers])
