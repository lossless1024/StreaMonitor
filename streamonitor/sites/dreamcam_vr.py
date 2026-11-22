from urllib.parse import urlparse, parse_qs

from parameters import VR_FORMAT_SUFFIX

from streamonitor.downloaders.fmp4s_wss import getVideoWSSVR
from streamonitor.sites.dreamcam import DreamCam


class DreamCamVR(DreamCam):
    site = 'DreamCamVR'
    siteslug = 'DCVR'

    _stream_type = 'video3D'
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
