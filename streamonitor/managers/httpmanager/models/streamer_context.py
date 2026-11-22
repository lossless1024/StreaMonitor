from __future__ import annotations

from typing import Dict, TypedDict, TYPE_CHECKING


if TYPE_CHECKING:
    from streamonitor.bot import Bot
    from streamonitor.models.video_data import VideoData


class StreamerContext(TypedDict):
    streamer: Bot
    sort_by_size: bool
    video_to_play: VideoData | None
    refresh_freq: int | None
    videos: Dict[str, VideoData]
    total_size: int
    has_error: bool
    recordings_error_message: str | None
    theater_mode: bool
    confirm_deletes: bool
