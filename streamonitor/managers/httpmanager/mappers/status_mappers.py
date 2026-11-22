from streamonitor.enums import Status


web_status_lookup = {
    Status.PUBLIC: "Online",
    Status.OFFLINE: "Offline",
    Status.PRIVATE: "Private Show",
    Status.NOTRUNNING: "Not Running",
    Status.RATELIMIT: "Rate-limited",
    Status.NOTEXIST: "No Such Streamer",
    Status.ERROR: "Error on Download",
    Status.UNKNOWN: "Unknown Error",
    Status.RESTRICTED: "Restricted: Geo-blocked?"
}

status_icons_lookup = {
    Status.UNKNOWN: "help-circle",
    Status.PUBLIC: "eye",
    Status.OFFLINE: "video-off",
    Status.LONG_OFFLINE: "video-off",
    Status.PRIVATE: "eye-off",
    Status.RATELIMIT: "alert-octagon",
    Status.NOTEXIST: "minus-circle",
    Status.NOTRUNNING: "bell-off",
    Status.ERROR: "alert-triangle",
    Status.RESTRICTED: "x-octagon"
}