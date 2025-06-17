import os

from streamonitor.utils import get_mimetype
from streamonitor.utils import human_file_size


class VideoData:
    filename: str
    mimetype: str
    abs_path: str
    shortname: str
    filesize: int = 0
    human_readable_filesize: str = '0'
    play = False

    def __init__(self, file: os.DirEntry, abs_path: str, shortname: str, is_play_video: bool):
        stats = file.stat()
        self.filename = file.name
        self.mimetype = get_mimetype(abs_path)
        self.abs_path = abs_path
        self.shortname = shortname
        self.filesize = stats.st_size
        self.human_readable_filesize = human_file_size(stats.st_size)
        self.play = is_play_video