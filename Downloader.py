import zmq
import streamonitor.config as config
from streamonitor.managers.httpmanager import HTTPManager
from streamonitor.managers.climanager import CLIManager
from streamonitor.managers.zmqmanager import ZMQManager
import streamonitor.sites  # must have


def main():
    streamers = config.loadStreamers()

    console_manager = CLIManager(streamers)
    console_manager.start()

    socket = zmq.Context.instance().socket(zmq.REP)
    socket.bind("tcp://*:6969")
    zmq_manager = ZMQManager(streamers, socket)
    zmq_manager.start()

    http_manager = HTTPManager(streamers)
    http_manager.start()


main()
