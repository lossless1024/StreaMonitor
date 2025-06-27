import mimetypes
import os
import logging
import re


logger = logging.getLogger(__name__)


class VideoData:
    filename: str
    mimetype: str
    abs_path: str
    shortname: str
    filesize: int = 0
    human_readable_filesize: str = '0'
    play = False

    def __init__(self, file: os.DirEntry, username: str):
        from streamonitor.utils.human_file_size import human_file_size
        self._stat = file.stat()
        self.username = username
        self.filename = file.name
        self.abs_path = os.path.abspath(file.path)
        self.filesize = self._stat.st_size
        self.human_readable_filesize = human_file_size(self._stat.st_size)

    @property
    def shortname(self):
        match = re.match(rf"{self.username}-(?P<shortname>\d{{8}}-\d*)\.", self.filename, re.IGNORECASE)
        if match:
            return match.group('shortname')
        else:
            return self.filename

    @property
    def mimetype(self):
        mimetype = 'application/octet-stream'
        # if we lie about this, chrome will play it
        # need to look at alternatives for firefox
        if self.abs_path is not None and self.abs_path.lower().endswith('.mkv'):
            mimetype = 'video/mp4'
        try:
            mimetype = mimetypes.guess_type(self.abs_path)[0]
        except Exception as e:
            logger.error(e)
        return mimetype
