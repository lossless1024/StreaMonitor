import zmq
import sys
import signal
import streamonitor.config as config
from streamonitor.managers.httpmanager import HTTPManager
from streamonitor.managers.climanager import CLIManager
from streamonitor.managers.zmqmanager import ZMQManager
from streamonitor.managers.outofspace_detector import OOSDetector
from streamonitor.clean_exit import CleanExit
import streamonitor.sites  # must have


def main():
    if not OOSDetector.disk_space_good():
        print(OOSDetector.under_threshold_message)
        sys.exit(1)

    streamers = config.loadStreamers()

    clean_exit = CleanExit(streamers).clean_exit
    signal.signal(signal.SIGINT, clean_exit)
    signal.signal(signal.SIGTERM, clean_exit)
    signal.signal(signal.SIGABRT, clean_exit)

    oos_detector = OOSDetector(streamers)
    oos_detector.start()

    console_manager = CLIManager(streamers)
    console_manager.start()

    socket = zmq.Context.instance().socket(zmq.REP)
    socket.bind("tcp://*:6969")
    zmq_manager = ZMQManager(streamers, socket)
    zmq_manager.start()

    http_manager = HTTPManager(streamers)
    http_manager.start()


main()
