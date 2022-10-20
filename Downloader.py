import zmq
import signal
import streamonitor.config as config
from streamonitor.managers.httpmanager import HTTPManager
from streamonitor.managers.climanager import CLIManager
from streamonitor.managers.zmqmanager import ZMQManager
from streamonitor.clean_exit import CleanExit
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

    clean_exit = CleanExit(streamers).clean_exit
    signal.signal(signal.SIGINT, clean_exit)
    signal.signal(signal.SIGTERM, clean_exit)
    signal.signal(signal.SIGABRT, clean_exit)


if __name__ == '__main__':
    main()
