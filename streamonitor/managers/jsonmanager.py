import json


class JsonWorker:
    def load(filepath: str):
        '''
        Loads json file from filepath as dict
        '''
        with open(filepath, "r") as f:
            return json.load(f)

    def save(filepath: str, data: dict):
        '''
        Saves data as json file to filepath
        '''
        with open(filepath, "w") as f:
            json.dump(data, f)
