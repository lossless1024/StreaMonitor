import os
import sys
import streamonitor.config as config
from streamonitor.managers.bulk_status_manager import BulkStatusManager
from streamonitor.managers.httpmanager import HTTPManager
from streamonitor.managers.climanager import CLIManager
from streamonitor.managers.zmqmanager import ZMQManager
from streamonitor.managers.outofspace_detector import OOSDetector
from streamonitor.clean_exit import CleanExit
import streamonitor.sites  # must have

        
def is_docker():
    path = '/proc/self/cgroup'
    return (
        os.path.exists('/.dockerenv') or
        os.path.isfile(path) and any('docker' in line for line in open(path))
    )


def main():
    if not OOSDetector.disk_space_good():
        print(OOSDetector.under_threshold_message)
        sys.exit(1)

    streamers = config.loadStreamers()

    clean_exit = CleanExit(streamers)

    oos_detector = OOSDetector(streamers)
    oos_detector.start()

    bulk_status_manager = BulkStatusManager(streamers)
    bulk_status_manager.start()

    if not is_docker():
        console_manager = CLIManager(streamers)
        console_manager.start()

    zmq_manager = ZMQManager(streamers)
    zmq_manager.start()

    http_manager = HTTPManager(streamers)
    http_manager.start()


main()
