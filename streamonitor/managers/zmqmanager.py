from streamonitor.manager import Manager
import streamonitor.log as log


class ZMQManager(Manager):
    def __init__(self, streamers, socket):
        super().__init__(streamers)
        self.socket = socket
        self.logger = log.Logger("manager_zmq")

    def reply(self, msg):
        self.socket.send_string(msg)

    def run(self):
        while True:
            line = self.socket.recv_string()
            self.logger.info("[ZMQ] " + line)
            reply = self.execCmd(line)
            self.reply(reply)
