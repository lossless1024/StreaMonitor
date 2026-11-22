import zmq
from streamonitor.manager import Manager
import streamonitor.log as log


class ZMQManager(Manager):
    def __init__(self, streamers):
        super().__init__(streamers)
        self.logger = log.Logger("manager_zmq")

    def run(self):
        with zmq.Context.instance().socket(zmq.REP) as socket:
            socket.bind("tcp://*:6969")
            while True:
                line = socket.recv_string()
                self.logger.info("[ZMQ] " + line)
                reply = self.execCmd(line)
                if type(reply) is str:
                    socket.send_string(reply)
                else:
                    socket.send_string('')
