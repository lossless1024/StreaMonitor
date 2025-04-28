from streamonitor.bot import Bot


class InvalidStreamer:
    username = 'invalid!'
    site = 'invalid!'
    status_icon = 'invalid!'

    def __init__(self, username, site):
        self.username = username
        self.site = site
        self.status_icon = Bot.status_icons.get(Bot.Status.NOTEXIST)
    
    def status(self):
        return Bot.status_messages.get(Bot.Status.NOTEXIST)