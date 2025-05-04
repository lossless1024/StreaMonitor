from __future__ import annotations

import os
from typing import Dict, TYPE_CHECKING

from parameters import WEB_STATUS_FREQUENCY, WEB_THEATER_MODE
import streamonitor.log as log
from .short_name import short_name
from .confirm_deletes import confirm_deletes

if(TYPE_CHECKING):
    from streamonitor.bot import Bot
    from streamonitor.models import StreamerContext


_logger = log.Logger("utils")
    

def get_streamer_context(streamer: Bot, sort_by_size: bool, play_video: str, user_agent: str) -> StreamerContext:
    from streamonitor.models.video_data import VideoData
    #videos = []
    videos: Dict[str, VideoData] = {}
    has_error = False
    recordings_error_message = None
    total_size = 0
    video_to_play: VideoData | None = None
    if(os.path.isdir(streamer.outputFolder)):
        try:
            for elem in os.scandir(streamer.outputFolder):
                if(elem.is_dir()):
                    continue
                else:
                    abs_path = os.path.abspath(elem.path)
                    shortname = short_name(elem.name, streamer.username)
                    video = VideoData(elem, abs_path, shortname, play_video == elem.name)
                    if(video.play):
                        video_to_play = video
                    total_size += video.filesize
                    videos[video.filename] = video
        except Exception as e:
            has_error = True
            recordings_error_message = repr(e)
            _logger.warning(e)
        if(sort_by_size):
            videos = dict(sorted(videos.items(), key=lambda item: item[1].filesize, reverse=True))
        else:
            videos = dict(sorted(videos.items(), reverse=True))
    context: StreamerContext = {
        'streamer': streamer,
        'sort_by_size': sort_by_size,
        'video_to_play': video_to_play,
        'refresh_freq': WEB_STATUS_FREQUENCY,
        'videos': videos,
        'total_size': total_size,
        'has_error': has_error,
        'recordings_error_message': recordings_error_message,
        'theater_mode': WEB_THEATER_MODE,
        'confirm_deletes': confirm_deletes(user_agent),
    }
    return context