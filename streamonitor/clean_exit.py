import time


class CleanExit:
    def __init__(self, streamers):
        self.streamers = streamers

    def clean_exit(self, a, b):
        for streamer in self.streamers:
            streamer.stop(None, None, True)
        for streamer in self.streamers:
            while streamer.is_alive():
                time.sleep(1)

