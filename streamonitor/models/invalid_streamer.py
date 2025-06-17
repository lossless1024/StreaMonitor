from streamonitor.enums import Status
from streamonitor.mappers import status_icons_lookup


class InvalidStreamer:
    username = 'invalid!'
    site = 'invalid!'
    status_icon = 'invalid!'

    def __init__(self, username, site):
        self.username = username
        self.site = site
        self.status_icon = status_icons_lookup.get(Status.NOTEXIST)
    
    def status(self):
        return status_icons_lookup.get(Status.NOTEXIST)
