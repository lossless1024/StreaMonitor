import requests
from urllib.parse import urlparse, parse_qs

from parameters import VR_FORMAT_SUFFIX
from streamonitor.bot import Bot
from streamonitor.downloaders.fmp4s_wss import getVideoWSSVR
from streamonitor.enums import Status


class DreamCamVR(Bot):
    site = 'DreamCamVR'
    siteslug = 'DCVR'

    vr_frame_format_map = {
        'FISHEYE': 'F',
        'PANORAMIC': 'P',
        'CIRCULAR': 'C',
    }

    def __init__(self, username):
        super().__init__(username)
        self.getVideo = getVideoWSSVR
        self.stopDownloadFlag = False

    @property
    def filename_extra_suffix(self):
        vr_suffix = ''
        if not VR_FORMAT_SUFFIX:
            return vr_suffix

        video_url = self.getVideoUrl()
        query = parse_qs(urlparse(video_url).query)
        if 'stereoPacking' in query:
            vr_packing = query["stereoPacking"][0]
            vr_suffix += f'_{vr_packing}'
        if 'frameFormat' in query and "horizontalAngle" in query:
            vr_frame_format = self.vr_frame_format_map[query["frameFormat"][0]]
            vr_angle = query["horizontalAngle"][0]
            vr_suffix += f'_{vr_frame_format}{vr_angle}'
        return vr_suffix

    def getVideoUrl(self):
        return self.lastInfo['streamUrl']

    def getStatus(self):
        r = requests.get('https://bss.dreamcamtrue.com/api/clients/v1/broadcasts/models/' + self.username, headers=self.headers)
        if r.status_code != 200:
            return Status.UNKNOWN

        self.lastInfo = r.json()

        if self.lastInfo["broadcastStatus"] in ["public"]:
            return Status.PUBLIC
        if self.lastInfo["broadcastStatus"] in ["private"]:
            return Status.PRIVATE
        if self.lastInfo["broadcastStatus"] in ["away", "offline"]:
            return Status.OFFLINE
        self.logger.warn(f'Got unknown status: {self.lastInfo["broadcastStatus"]}')
        return Status.UNKNOWN


Bot.loaded_sites.add(DreamCamVR)
