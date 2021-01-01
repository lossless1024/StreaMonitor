import zmq
import config
from manager import Manager
from httpmanager import HTTPManager
import sites  # must have


def main():
    streamers = config.loadStreamers()

    console_manager = Manager(streamers, "console")
    console_manager.start()

    socket = zmq.Context.instance().socket(zmq.REP)
    socket.bind("tcp://*:6969")
    zmq_manager = Manager(streamers, "zmq", socket)
    zmq_manager.start()

    http_manager = HTTPManager(streamers)
    http_manager.start()


main()
