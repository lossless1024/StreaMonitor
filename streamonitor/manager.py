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
        assert mode in ['console', 'zmq']
        self.streamers = streamers
        self.mode = mode
        self.socket = socket
        self.logger = log.Logger("manager_" + mode)

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

            if command == 'add':
                if username and site:
                    try:
                        user = Bot.createInstance(username, site)
                        self.streamers[user.username] = user
                        self.streamers[user.username].start()
                        self.reply("Added [" + self.streamers[user.username].siteslug + "] " + user.username)
                    except:
                        self.reply("Failed to add")
                else:
                    self.reply("Missing value(s)")

            elif command == 'remove':
                try:
                    self.streamers[username].stop(None, None)
                    self.streamers[username].logger.handlers = []
                    self.streamers.pop(username)
                    self.reply("OK")
                except KeyError:
                    self.reply("No such username")
                except Exception as e:
                    logger.error(e)
                    self.reply("Failed to remove streamer")

            elif command == 'start':
                try:
                    self.streamers[username].start()
                    self.reply("OK")
                except KeyError:
                    self.reply("No such username")
                except Exception as e:
                    logger.error(e)
                    self.reply("Failed to start")

            elif command == 'stop':
                try:
                    self.streamers[username].stop(None, None)
                    self.reply("OK")
                except KeyError:
                    self.reply("No such username")
                except Exception as e:
                    logger.error(e)
                    self.reply("Failed to stop")

            elif command == 'status':
                output = [["Username", "Site", "Started", "Status"]]
                streamer_list = list(self.streamers.keys())
                streamer_list.sort(key=lambda v: v.upper())
                for s in streamer_list:
                    streamer = self.streamers[s]
                    output.append([streamer.username,
                                   streamer.site,
                                   streamer.running,
                                   streamer.status()])
                self.reply("Status:\n" + AsciiTable(output).table)

            elif command == 'status2':
                streamer_list = list(self.streamers.keys())
                streamer_list.sort(key=lambda v: v.upper())
                maxlen = max([len(name) for name in streamer_list])
                termwidth = terminaltables.terminal_io.terminal_size()[0]
                table_nx = math.floor(termwidth/(maxlen+3))

                for site in Bot.loaded_sites:
                    output = 'Status:\n'
                    output += site.site + '\n'
                    output += ('+' + '-'*(maxlen+2))*table_nx + '+\n'
                    site_name = site.site
                    i = 0
                    for s in streamer_list:
                        streamer = self.streamers[s]
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

            config.save_config([self.streamers[x].export() for x in self.streamers])
