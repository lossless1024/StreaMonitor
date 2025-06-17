import mimetypes

import streamonitor.log as log

_logger = log.Logger("utils")

def get_mimetype(file):
    mimetype = 'video/mp4'
    # if we lie about this, chrome will play it
    # need to look at alternatives for firefox
    if(file is not None and file.lower().endswith('.mkv')):
        mimetype = 'video/mp4'
    try:
        mimetype = mimetypes.guess_type(file)[0]
    except Exception as e:
        _logger.warning(e)
    return mimetype