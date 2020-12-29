import json
import sys

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
