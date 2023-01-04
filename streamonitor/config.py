import json
import sys
import time

from streamonitor.bot import Bot

config_loc = "config.json"


def load_config():
    try:
        with open(config_loc, "r+") as f:
            return json.load(f)
    except FileNotFoundError:
        with open(config_loc, "w+") as f:
            json.dump([], f, indent=4)
            return []
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
    streamers = []
    for streamer in load_config():
        room_id = streamer.get('room_id')
        username = streamer["username"]
        site = streamer["site"]
        if room_id:
            streamer_bot = Bot.str2site(site)(username, room_id=room_id)
        else:
            streamer_bot = Bot.str2site(site)(username)
        streamers.append(streamer_bot)
        streamer_bot.start()
        if streamer["running"]:
            streamer_bot.restart()
            time.sleep(0.1)
    return streamers
