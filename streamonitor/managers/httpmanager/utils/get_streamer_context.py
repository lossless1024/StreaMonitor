from __future__ import annotations

from typing import Dict, TYPE_CHECKING

import streamonitor.log as log
from parameters import WEB_STATUS_FREQUENCY, WEB_THEATER_MODE
from .confirm_deletes import confirm_deletes
from streamonitor.models.video_data import VideoData

if TYPE_CHECKING:
    from streamonitor.bot import Bot
    from streamonitor.managers.httpmanager.models import StreamerContext


_logger = log.Logger("utils")
    

def get_streamer_context(streamer: Bot, sort_by_size: bool, play_video: str, user_agent: str) -> StreamerContext:
    videos: Dict[str, VideoData] = {}
    has_error = False
    recordings_error_message = None
    for video in streamer.video_files:
        videos[video.filename] = video
    if sort_by_size:
        videos = dict(sorted(videos.items(), key=lambda item: item[1].filesize, reverse=True))
    else:
        videos = dict(sorted(videos.items(), reverse=True))

    context: StreamerContext = {
        'streamer': streamer,
        'sort_by_size': sort_by_size,
        'video_to_play': videos.get(play_video),
        'refresh_freq': WEB_STATUS_FREQUENCY,
        'videos': videos,
        'total_size': streamer.video_files_total_size,
        'has_error': has_error,
        'recordings_error_message': recordings_error_message,
        'theater_mode': WEB_THEATER_MODE,
        'confirm_deletes': confirm_deletes(user_agent),
    }
    return context
