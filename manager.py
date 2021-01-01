from threading import Thread
from terminaltables import AsciiTable
import config
import log


class Manager(Thread):
    def __init__(self, streamers, mode, socket=None):
        super().__init__()
        self.streamers = streamers
        self.mode = mode
        self.socket = socket

    def reply(self, msg):
        if self.mode == "zmq":
            self.socket.send_string(msg)
        if self.mode == "console":
            print(msg)

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
                        self.streamers[username] = str2site(site)(username)
                        self.streamers[username].start()
                        self.reply("Added [" + self.streamers[username].siteslug + "] " + username)
                    except:
                        self.reply("Failed to add")
                else:
                    self.reply("Missing value(s)")

            if command == 'remove':
                self.streamers[username].stop(None, None)
                self.streamers[username].logger.handlers = []
                self.streamers.pop(username)
                self.reply("OK")

            if command == 'start':
                try:
                    self.streamers[username].start()
                    self.reply("OK")
                except:
                    self.reply("Failed to start")

            if command == 'stop':
                try:
                    self.streamers[username].stop(None, None)
                    self.reply("OK")
                except Exception as e:
                    logger.error(e)
                    self.reply("Failed to stop")

            if command == 'status':
                output = [["Site", "Username", "Started", "Status"]]
                for streamer in self.streamers:
                    output.append([self.streamers[streamer].site,
                                   self.streamers[streamer].username,
                                   self.streamers[streamer].running,
                                   self.streamers[streamer].status()])
                self.reply(AsciiTable(output).table)

            config.save_config([self.streamers[x].export() for x in self.streamers])
