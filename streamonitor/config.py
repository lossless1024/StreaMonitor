import json
import os
import sys
import time

from streamonitor.bot import Bot
from streamonitor.log import Logger

logger = Logger('[CONFIG]').get_logger()
config_loc = "config.json"


def load_config():
    try:
        with open(config_loc, "r+") as f:
            return json.load(f)
    except FileNotFoundError:
        with open(config_loc, "w+") as f:
            json.dump([], f, indent=4)
            return []
    except ValueError:
        logger.error('Corrupted config.json')
        sys.exit(1)
    except Exception as e:
        logger.exception(e)
        sys.exit(1)


def save_config(config):
    try:
        with open(config_loc+'.tmp', "w+") as f:
            json.dump(config, f, indent=4)
        if os.path.exists(config_loc+'.bak'):
            os.remove(config_loc+'.bak')
        if os.path.exists(config_loc):
            os.rename(config_loc, config_loc+'.bak')
        if not os.path.exists(config_loc) and os.path.exists(config_loc+'.tmp'):
            os.rename(config_loc+'.tmp', config_loc)
        return True
    except Exception as e:
        logger.exception(e)
        sys.exit(1)


def saveStreamers(streamers):
    save_config([s.export() for s in streamers])


def loadStreamers():
    streamers = []
    for streamer in load_config():
        username = streamer["username"]
        site = streamer["site"]

        bot_class = Bot.str2site(site)
        if not bot_class:
            logger.warning(f'Unknown site: {site} (user: {username})')
            continue

        streamer_bot = bot_class.fromConfig(streamer)
        streamers.append(streamer_bot)
        streamer_bot.start()
        time.sleep(0.1)
    saveStreamers(streamers)
    return streamers
