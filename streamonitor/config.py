import json
import os
import sys
import time

from streamonitor.bot import Bot
from streamonitor.log import Logger

logger = Logger('[CONFIG]').get_logger()
config_loc = "config.json"
favorites_loc = "config.favorites.json"
favorites_only = False


def _model_key(entry):
    if not isinstance(entry, dict):
        return None
    username = entry.get("username")
    site = entry.get("site")
    if not username or not site:
        return None
    return str(username).lower(), str(site).lower()


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
        with open(config_loc, "w+") as f:
            json.dump(config, f, indent=4)
        return True
    except Exception as e:
        logger.exception(e)
        sys.exit(1)


def saveStreamers(streamers):
    save_config([s.export() for s in streamers])


def load_favorites_config():
    try:
        with open(favorites_loc, "r") as f:
            entries = json.load(f)
            return entries if isinstance(entries, list) else []
    except FileNotFoundError:
        return None
    except (ValueError, json.JSONDecodeError):
        logger.warning("Corrupted config.favorites.json; keeping current favorites")
        return None
    except Exception as e:
        logger.exception(e)
        return None


def ensure_favorites_config(base_entries=None):
    if base_entries is None:
        base_entries = load_config()
    entries = load_favorites_config()
    if entries is not None:
        return entries
    return sync_favorites_config(base_entries)


def sync_favorites_config(base_entries=None, persist=True):
    if base_entries is None:
        base_entries = load_config()
    existing_entries = load_favorites_config()
    if existing_entries is None:
        existing_entries = []
        if os.path.exists(favorites_loc):
            persist = False
    existing = {}
    for entry in existing_entries:
        key = _model_key(entry)
        if key:
            existing[key] = entry

    synchronized = []
    for base_entry in base_entries:
        if not isinstance(base_entry, dict):
            continue
        key = _model_key(base_entry)
        if key is None:
            continue
        entry = dict(base_entry)
        entry["favorite"] = bool(existing.get(key, {}).get("favorite", False))
        synchronized.append(entry)

    if persist:
        try:
            with open(favorites_loc, "w") as f:
                json.dump(synchronized, f, indent=4)
        except Exception as e:
            logger.exception(e)
    return synchronized


def set_favorite(username, site, favorite):
    if os.path.exists(favorites_loc) and load_favorites_config() is None:
        return False
    entries = sync_favorites_config()
    key = (str(username).lower(), str(site).lower())
    found = False
    for entry in entries:
        if _model_key(entry) == key:
            entry["favorite"] = bool(favorite)
            found = True
            break
    if not found:
        return False
    try:
        with open(favorites_loc, "w") as f:
            json.dump(entries, f, indent=4)
        return True
    except Exception as e:
        logger.exception(e)
        return False


def load_favorite_streamers():
    favorites = sync_favorites_config()
    return [entry for entry in favorites if entry.get("favorite") is True]


def loadStreamers(favorites=False):
    streamers = []
    global favorites_only
    favorites_only = bool(favorites)
    base_entries = load_config()
    ensure_favorites_config(base_entries)
    entries = load_favorite_streamers() if favorites else base_entries
    for streamer in entries:
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
    if not favorites:
        saveStreamers(streamers)
    return streamers
