from enum import Enum


class Status(Enum):
    UNKNOWN = 1
    NOTRUNNING = 2
    ERROR = 3
    RESTRICTED = 1403
    PUBLIC = 200
    PRIVATE = 300
    EXCLUSIVE = 301
    HIDDEN = 302
    GROUP = 303
    NOTEXIST = 400
    CONNECTED = 402
    AWAY = 403
    OFFLINE = 404
    LONG_OFFLINE = 410
    RATELIMIT = 429
