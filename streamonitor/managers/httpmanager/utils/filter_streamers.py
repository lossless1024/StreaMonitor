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


def streamer_list(streamers: List[Bot], request):
    username_filter = request.args.get("filter-username", None)
    site_filter = request.args.get("filter-site", None)
    status_filter = request.args.get("filter-status", 'all')

    if username_filter or site_filter or (status_filter and status_filter != 'all'):
        streamers_list = list(
            filter(
                lambda x: filter_streamers(x, username_filter, site_filter, status_filter),
                streamers
            )
        )
        filtered = True
    else:
        streamers_list = streamers.copy()
        filtered = False

    context = {
        'is_filtered': filtered,
        'username_filter': username_filter,
        'site_filter': site_filter,
        'status_filter': status_filter,
    }

    return streamers_list, context


def set_streamer_list_cookies(context, request, response):
    username_filter = context.get("username_filter")
    site_filter = context.get("site_filter")
    status_filter = context.get("status_filter")
    filtered = context.get('is_filtered')

    set_filters = request.args.get("set_filters")
    if set_filters and filtered:
        if username_filter:
            response.set_cookie('username_filter', username_filter)
        if site_filter:
            response.set_cookie('site_filter', site_filter)
        response.set_cookie('status_filter', status_filter)
    elif set_filters and not filtered:
        response.delete_cookie('username_filter')
        response.delete_cookie('site_filter')
        response.delete_cookie('status_filter')
