DOWNLOADS_DIR = 'downloads'
MIN_FREE_DISK_PERCENT = 1.0  # in %
DEBUG = False

# You can enter a number to select a specific height.
# Use a huge number here and closest match to get the highest resolution variant
# Eg: 240, 360, 480, 720, 1080, 1440, 99999
WANTED_RESOLUTION = 1080

# Specify match type when specified height
# Possible values: exact, exact_or_least_higher, exact_or_highest_lower, closest
# Beware of the exact policy. Nothing gets downloaded if the wanted resolution is not available
WANTED_RESOLUTION_PREFERENCE = 'closest'

# Video files will be saved with the specified extension.
# For example, if '.mkv' is used, the file will be saved in the mkv format and you will be able to
# watch it while it's being downloaded.
# Also, if someting goes wrong, you will still be able to play the partially downloaded mkv file, 
# as opposed to a mp4 file.
VIDEO_FILE_EXTENSION = '.mkv'
