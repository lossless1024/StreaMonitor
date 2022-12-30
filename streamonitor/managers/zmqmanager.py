import zmq
from streamonitor.manager import Manager
import streamonitor.log as log


class ZMQManager(Manager):
    def __init__(self, streamers):
        super().__init__(streamers)
        self.logger = log.Logger("manager_zmq")
        self.socket = zmq.Context.instance().socket(zmq.REP)
        self.socket.bind("tcp://*:6969")

    def run(self):
        while True:
            line = self.socket.recv_string()
            self.logger.info("[ZMQ] " + line)
            reply = self.execCmd(line)
            if type(reply) is str:
                self.socket.send_string(reply)
            else:
                self.socket.send_string('')
