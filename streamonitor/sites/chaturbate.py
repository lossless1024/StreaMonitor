import re
import m3u8
import requests
from urllib.parse import urljoin
from streamonitor.bot import Bot
from streamonitor.enums import Status, Gender
from parameters import WANTED_RESOLUTION, WANTED_RESOLUTION_PREFERENCE


class Chaturbate(Bot):
    site = "Chaturbate"
    siteslug = "CB"
    bulk_update = True

    _GENDER_MAP = {
        "f": Gender.FEMALE,
        "m": Gender.MALE,
        "s": Gender.TRANS,
        "c": Gender.BOTH,
    }

    def __init__(self, username):
        super().__init__(username)
        self.sleep_on_offline = 30
        self.sleep_on_error = 60

    def getWebsiteURL(self):
        return "https://www.chaturbate.com/" + self.username

    def getVideoUrl(self):
        if self.bulk_update:
            self.getStatus()
        url = self.lastInfo["url"]
        if not url:
            return None

        if "llhls.m3u8" in url:
            return self._getCmafPlaylist(url)

        if self.lastInfo.get("cmaf_edge"):
            url = url.replace("playlist.m3u8", "playlist_sfm4s.m3u8")
            url = re.sub("live-.+amlst", "live-c-fhls/amlst", url)

        return self.getWantedResolutionPlaylist(url)

    def _getCmafPlaylist(self, url):
        result = self.session.get(url, headers=self.headers)
        master = m3u8.loads(result.text)

        audio_uris = {}
        for media in master.media:
            if media.type == "AUDIO":
                audio_uris[media.group_id] = urljoin(url, media.uri)

        variants = []
        for playlist in master.playlists:
            stream_info = playlist.stream_info
            resolution = (
                stream_info.resolution
                if type(stream_info.resolution) is tuple
                else (0, 0)
            )
            audio_group = getattr(stream_info, "audio", None)
            audio_url = audio_uris.get(audio_group) if audio_group else None
            variants.append(
                {
                    "url": urljoin(url, playlist.uri),
                    "resolution": resolution,
                    "bandwidth": stream_info.bandwidth,
                    "audio_url": audio_url,
                }
            )

        if not variants:
            return url

        for variant in variants:
            w, h = variant["resolution"]
            if w < h:
                variant["resolution_diff"] = w - WANTED_RESOLUTION
            else:
                variant["resolution_diff"] = h - WANTED_RESOLUTION

        variants.sort(key=lambda a: abs(a["resolution_diff"]))

        if WANTED_RESOLUTION_PREFERENCE == "exact":
            selected = next(
                (v for v in variants if abs(v["resolution_diff"]) == 0), variants[0]
            )
        else:
            selected = variants[0]

        self.logger.info(
            f"Selected {selected['resolution'][0]}x{selected['resolution'][1]} resolution (CMAF)"
        )
        return (selected["url"], selected["audio_url"])

    @staticmethod
    def _parseStatus(status):
        if status == "public":
            return Status.PUBLIC
        elif status in ["private", "hidden"]:
            return Status.PRIVATE
        else:
            return Status.OFFLINE

    def getStatus(self):
        headers = {"X-Requested-With": "XMLHttpRequest"}
        data = {"room_slug": self.username, "bandwidth": "high"}

        try:
            r = requests.post(
                "https://chaturbate.com/get_edge_hls_url_ajax/",
                headers=headers,
                data=data,
            )
            self.lastInfo = r.json()
            status = self._parseStatus(self.lastInfo["room_status"])
            if status == status.PUBLIC and not self.lastInfo["url"]:
                status = status.RESTRICTED
        except:
            status = Status.RATELIMIT

        self.ratelimit = status == Status.RATELIMIT
        return status

    @classmethod
    def getStatusBulk(cls, streamers):
        for streamer in streamers:
            if not isinstance(streamer, Chaturbate):
                continue

        session = requests.Session()
        session.headers.update(cls.headers)
        r = session.get(
            "https://chaturbate.com/affiliates/api/onlinerooms/?format=json&wm=DkfRj",
            timeout=10,
        )

        try:
            data = r.json()
        except requests.exceptions.JSONDecodeError:
            print("Failed to parse JSON response")
            return
        data_map = {str(model["username"]).lower(): model for model in data}

        for streamer in streamers:
            model_data = data_map.get(streamer.username.lower())
            if not model_data:
                streamer.setStatus(Status.OFFLINE)
                continue
            if model_data.get("gender"):
                streamer.gender = cls._GENDER_MAP.get(model_data.get("gender"))
            if model_data.get("country"):
                streamer.country = model_data.get("country", "").upper()
            status = cls._parseStatus(model_data["current_show"])
            if status == status.PUBLIC:
                if streamer.sc in [status.PUBLIC, Status.RESTRICTED]:
                    continue
                status = streamer.getStatus()
            if status == Status.UNKNOWN:
                print(
                    f"[{streamer.siteslug}] {streamer.username}: Bulk update got unknown status: {status}"
                )
            streamer.setStatus(status)
