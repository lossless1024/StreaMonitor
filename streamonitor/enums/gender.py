from enum import Enum


class Gender(Enum):
    UNKNOWN = None
    FEMALE = 1
    MALE = 2
    BOTH = 3
    TRANS_WOMAN = 5
    TRANS_MAN = 6
    TRANS = 7
    FEMALE_COUPLE = 9
    MALE_COUPLE = 10


GENDER_DATA = {
    Gender.UNKNOWN: {'name': 'Unknown gender', 'icon': '', 'bs-icon': '', 'color': None},
    Gender.FEMALE: {'name': 'Female', 'icon': '♀', 'bs-icon': 'fa-venus', 'color': 'pink'},
    Gender.MALE: {'name': 'Male', 'icon': '♂', 'bs-icon': 'fa-mars', 'color': 'aliceblue'},
    Gender.BOTH: {'name': 'Both (group)', 'icon': '♀♂', 'bs-icon': 'fa-venus-mars', 'color': 'lime'},
    Gender.TRANS_WOMAN: {'name': 'Trans woman', 'icon': '⚥', 'bs-icon': 'fa-venus-mars', 'color': 'pink'},
    Gender.TRANS_MAN: {'name': 'Trans man', 'icon': '⚥', 'bs-icon': 'fa-venus-mars', 'color': 'aliceblue'},
    Gender.TRANS: {'name': 'Trans', 'icon': '⚥', 'bs-icon': 'fa-venus-mars', 'color': None},
    Gender.FEMALE_COUPLE: {'name': 'Female couple', 'icon': '', 'bs_icon': 'fa-venus-double', 'color': 'pink'}
}
