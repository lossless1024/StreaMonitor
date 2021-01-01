import json
import sys
from bot import Bot

config_loc = "config.json"


def load_config():
    try:
        with open(config_loc, "r+") as f:
            return json.load(f)
    except Exception as e:
        print(e)
        sys.exit(1)


def save_config(config):
    try:
        with open(config_loc, "w+") as f:
            json.dump(config, f, indent=4)

        return True
    except Exception as e:
        print(e)
        sys.exit(1)


def loadStreamers():
    streamers = {}
    for streamer in load_config():
        username = streamer["username"]
        site = streamer["site"]
        streamers[username] = Bot.str2site(site)(username)
        if streamer["running"]:
            streamers[username].start()
    return streamers
