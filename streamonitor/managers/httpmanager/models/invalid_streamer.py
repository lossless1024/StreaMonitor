from streamonitor.enums import Status


class InvalidStreamer:
    def __init__(self, username, site):
        self.username = username
        self.site = site
        self.sc = Status.UNKNOWN
