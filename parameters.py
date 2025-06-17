import os


DOWNLOADS_DIR = os.getenv("STRMNTR_DOWNLOAD_DIR", "downloads")
MIN_FREE_DISK_PERCENT = int(os.getenv("STRMNTR_MIN_FREE_SPACE", 5.0))  # in %
DEBUG = bool(os.getenv("STRMNTR_DEBUG", False))

# The camsoda bot ignores this setting in favor of a chrome useragent generated with the fake-useragent library
HTTP_USER_AGENT = os.getenv("STRMNTR_USER_AGENT", "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:135.0) Gecko/20100101 Firefox/135.0")

# Specify the full path to the ffmpeg binary. By default, ffmpeg found on PATH is used.
FFMPEG_PATH = 'ffmpeg'

# You can enter a number to select a specific height.
# Use a huge number here and closest match to get the highest resolution variant
# Eg: 240, 360, 480, 720, 1080, 1440, 99999
WANTED_RESOLUTION = int(os.getenv("STRMNTR_RESOLUTION", 1080))

# Specify match type when specified height
# Possible values: exact, exact_or_least_higher, exact_or_highest_lower, closest
# Beware of the exact policy. Nothing gets downloaded if the wanted resolution is not available
WANTED_RESOLUTION_PREFERENCE = os.getenv("STRMNTR_RESOLUTION_PREF", 'closest')

# Specify output container here
# Suggested values are 'mkv' or 'mp4'
CONTAINER = os.getenv("STRMNTR_CONTAINER", 'mp4')

# Specify the segment time in seconds
# If None, the video will be downloaded as a single file
# Example:
# 5 minutes
# SEGMENT_TIME = 300
# 1 hour
# SEGMENT_TIME = 3600
# Also see the ffmpeg documentation for the segment_time option
# You can specify time in hh:mm:ss format
# Example:
# 1 hour
# SEGMENT_TIME = '1:00:00'
SEGMENT_TIME = os.getenv("STRMNTR_SEGMENT_TIME", None)

# HTTP Manager configuration

# Bind address for the web server
# 0.0.0.0 for remote access from all host
WEBSERVER_HOST = os.getenv("STRMNTR_HOST", "127.0.0.1")
WEBSERVER_PORT = int(os.getenv("STRMNTR_PORT", 5000))

# set frequency in seconds of how often the streamer list will update
_str_list_frequency = os.getenv("STRMNTR_LIST_FREQ", "30")
WEB_LIST_FREQUENCY = int(_str_list_frequency) if _str_list_frequency and _str_list_frequency.isdecimal() else None 

# set frequency in seconds of how often the streamer's status will update on the recording page
_str_status_frequency = os.getenv("STRMNTR_STATUS_FREQ", "5")
WEB_STATUS_FREQUENCY = int(_str_status_frequency) if _str_status_frequency and _str_status_frequency.isdecimal else None

# set theater_mode
WEB_THEATER_MODE = bool(os.getenv("STRMNTR_THEATER_MODE", False))

# confirm deletes, default to mobile-only.
# set to empty string to disable
# set to "MOBILE" to explicitly confirm deletes only on mobile
# set to any other non-falsy value to always check
WEB_CONFIRM_DELETES = os.getenv("STRMNTR_CONFIRM_DEL", "MOBILE")

# Password for the web server
# If empty no auth required, else username admin and choosen password
WEBSERVER_PASSWORD = os.getenv("STRMNTR_PASSWORD", "admin")
