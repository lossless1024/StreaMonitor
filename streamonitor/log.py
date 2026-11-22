import logging
import parameters


class Logger(object):
    def __init__(self, name="__name__"):
        self.name = name
        self.formatter = logging.Formatter('%(asctime)s - %(levelname)s - {}: %(message)s'.format(name))
        self.handler = logging.StreamHandler()
        self.handler.setFormatter(self.formatter)

        self.logger = logging.getLogger(self.name)
        self.loglevel = logging.DEBUG if parameters.DEBUG else logging.INFO
        self.logger.setLevel(self.loglevel)
        self.logger.addHandler(self.handler)

    def get_logger(self):
        logger = logging.getLogger(self.name)
        logger.setLevel(self.loglevel)
        logger.addHandler(self.handler)
        return logger

    def debug(self, msg):
        self.logger.debug(msg)

    def warning(self, msg):
        self.logger.warning(msg)

    def error(self, msg):
        self.logger.error(msg)

    def info(self, msg):
        self.logger.info(msg)
