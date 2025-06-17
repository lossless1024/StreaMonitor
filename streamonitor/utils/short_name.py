import re


def short_name(filename, username):
        match = re.match(rf"{username}-(?P<shortname>\d{{8}}-\d*)\.", filename,  re.IGNORECASE)
        if match:
            return match.group('shortname')
        else:
            return filename