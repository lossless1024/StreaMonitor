import zmq
import config
from manager import Manager
from httpmanager import HTTPManager
from sites.chaturbate import Chaturbate
from sites.pornhublive import PornHubLive
from sites.bongacams import BongaCams

sites = [Chaturbate, PornHubLive, BongaCams]


def str2site(site):
    for sitecls in sites:
        if site.lower() == sitecls.site.lower() or site.lower() == sitecls.siteslug.lower():
            return sitecls


def main():
    streamers = {}
    for streamer in config.load_config():
        username = streamer["username"]
        site = streamer["site"]
        streamers[username] = str2site(site)(username)
        if streamer["running"]:
            streamers[username].start()

    console_manager = Manager(streamers, "console")
    console_manager.start()

    socket = zmq.Context.instance().socket(zmq.REP)
    socket.bind("tcp://*:6969")
    zmq_manager = Manager(streamers, "zmq", socket)
    zmq_manager.start()

    http_manager = HTTPManager(streamers)
    http_manager.start()

main()
