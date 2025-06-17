from typing import List, cast, Union

from streamonitor.bot import Bot
from streamonitor.enums import Status


def filter_streamers(streamer: Bot, username_filter: Union[str, None], site_filter: Union[str, None], status_filter: Union[str, None]):
    result = True
    if username_filter:
        result = result and cast(str, streamer.username).lower().startswith(username_filter.lower())
    if site_filter:
        result = result and streamer.site == site_filter
    if status_filter and status_filter == 'running':
        result = result and streamer.running
    elif status_filter and status_filter == 'rec':
        result = result and streamer.recording
    elif status_filter and status_filter != 'all':
        status = Status.OFFLINE.value if streamer.sc.value == Status.LONG_OFFLINE.value else streamer.sc.value
        result = result and status == int(status_filter)
    return result


def streamer_list(streamers: List[Bot], username_filter: Union[str, None], site_filter: Union[str, None], status_filter: Union[str, None]):
    if username_filter or site_filter or (status_filter and status_filter != 'all'):
        return (list(
            filter(
                lambda x: filter_streamers(x, username_filter, site_filter, status_filter),
                streamers
            )
        ), True)
    else:
        return streamers, False
