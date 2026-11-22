import time

from streamonitor.enums import Status
from streamonitor.managers.httpmanager.mappers import web_status_lookup, status_icons_lookup


def status_text(sc):
    if sc:
        return web_status_lookup.get(sc, web_status_lookup[Status.OFFLINE])
    else:
        return web_status_lookup.get(Status.UNKNOWN)


def status_icon(streamer):
    if streamer.recording:
        return 'arrow-down-circle'
    return status_icons_lookup.get(streamer.sc) or status_icons_lookup.get(Status.UNKNOWN)


def reltime(timestamp):
    """Human 'time ago' label for a unix timestamp. Empty for 0/None."""
    if not timestamp:
        return 'Never'
    delta = time.time() - timestamp
    if delta < 0:
        delta = 0
    minute, hour, day = 60, 3600, 86400
    if delta < minute:
        return 'just now'
    if delta < hour:
        n = int(delta // minute)
        return f'{n} min ago'
    if delta < day:
        n = int(delta // hour)
        return f'{n} hr ago'
    if delta < 7 * day:
        n = int(delta // day)
        return f'{n} day{"s" if n != 1 else ""} ago'
    if delta < 365 * day:
        n = int(delta // (7 * day))
        return f'{n} wk{"s" if n != 1 else ""} ago'
    n = int(delta // (365 * day))
    return f'{n} yr{"s" if n != 1 else ""} ago'


def abstime(timestamp):
    """Absolute date-time label (for tooltips). Empty for 0/None."""
    if not timestamp:
        return 'No recordings yet'
    return time.strftime('%Y-%m-%d %H:%M', time.localtime(timestamp))
