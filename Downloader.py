import os
import sys
import argparse
from datetime import datetime
import streamonitor.config as config
import streamonitor.bot as bot_module
from streamonitor.managers.bulk_status_manager import BulkStatusManager
from streamonitor.managers.httpmanager import HTTPManager
from streamonitor.managers.climanager import CLIManager
from streamonitor.managers.zmqmanager import ZMQManager
from streamonitor.managers.outofspace_detector import OOSDetector
from streamonitor.managers.config_watcher import ConfigWatcherManager
from streamonitor.clean_exit import CleanExit
import streamonitor.sites  # must have

        
def is_docker():
    path = '/proc/self/cgroup'
    return (
        os.path.exists('/.dockerenv') or
        os.path.isfile(path) and any('docker' in line for line in open(path))
    )


def main():
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument(
        '--favs',
        action='store_true',
        help='Load only models marked as favorite in config.favorites.json',
    )
    parser.add_argument(
        '--sf',
        action='store_true',
        help='Save recordings in the original single-folder layout',
    )
    args, _ = parser.parse_known_args()
    if args.sf:
        bot_module.DOWNLOADS_BY_DATE = False
        print("Download layout: single-folder (downloads/<model> [SITE])")
    elif bot_module.DOWNLOADS_BY_DATE:
        print(
            "Download layout: "
            f"{bot_module.DOWNLOADS_DIR}/{datetime.now().strftime(bot_module.DOWNLOAD_DATE_FORMAT)}"
        )
    else:
        print("Download layout: single-folder (downloads/<model> [SITE])")

    os.makedirs(bot_module.DOWNLOADS_DIR, exist_ok=True)
    if bot_module.DOWNLOADS_BY_DATE:
        dated_folder = os.path.join(
            bot_module.DOWNLOADS_DIR,
            datetime.now().strftime(bot_module.DOWNLOAD_DATE_FORMAT),
        )
        os.makedirs(dated_folder, exist_ok=True)

    if not OOSDetector.disk_space_good():
        print(OOSDetector.under_threshold_message)
        sys.exit(1)

    streamers = config.loadStreamers(favorites=args.favs)

    clean_exit = CleanExit(streamers)

    oos_detector = OOSDetector(streamers)
    oos_detector.start()

    bulk_status_manager = BulkStatusManager(streamers)
    bulk_status_manager.start()

    config_watcher = ConfigWatcherManager(
        streamers,
        favorites_only=args.favs,
    )
    config_watcher.start()

    if not is_docker() and sys.stdin and sys.stdin.isatty():
        console_manager = CLIManager(streamers)
        console_manager.start()

    zmq_manager = ZMQManager(streamers)
    zmq_manager.start()

    http_manager = HTTPManager(streamers)
    http_manager.start()


main()
