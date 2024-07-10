DOWNLOADS_DIR = 'downloads'
MIN_FREE_DISK_PERCENT = 1.0  # in %
DEBUG = False
HTTP_USER_AGENT = "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:75.0) Gecko/20100101 Firefox/75.0"

# You can enter a number to select a specific height.
# Use a huge number here and closest match to get the highest resolution variant
# Eg: 240, 360, 480, 720, 1080, 1440, 99999
WANTED_RESOLUTION = 1080

# Specify match type when specified height
# Possible values: exact, exact_or_least_higher, exact_or_highest_lower, closest
# Beware of the exact policy. Nothing gets downloaded if the wanted resolution is not available
WANTED_RESOLUTION_PREFERENCE = 'closest'

# Specify output container here
# Suggested values are 'mkv' or 'mp4'
CONTAINER = 'mp4'

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
SEGMENT_TIME = None
