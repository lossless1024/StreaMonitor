import sys
from streamonitor.manager import Manager
from streamonitor.clean_exit import CleanExit
import streamonitor.log as log

if sys.platform != "win32":
    import readline


class CLIManager(Manager):
    def __init__(self, streamers):
        super().__init__(streamers)
        self.logger = log.Logger("manager_cli")

    def run(self):
        while True:
            try:
                line = input("> ")
            except EOFError:
                self.do_quit()
                return
            reply = self.execCmd(line)
            if line == "quit":
                return
            self.logger.info(reply)

    def do_quit(self, _=None, __=None, ___=None):
        CleanExit(self.streamers)()
