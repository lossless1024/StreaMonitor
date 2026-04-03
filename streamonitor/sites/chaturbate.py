import re

import requests

from parameters import (
    CHB_CF_CLEARANCE,
    CHB_PROXY_TEST_URL,
    CHB_USER_AGENT,
    REQUESTS_PROXIES,
)
from streamonitor.bot import Bot
from streamonitor.enums import Gender, Status


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
        self._proxy_test_logged = False

        if CHB_USER_AGENT:
            self.session.headers["User-Agent"] = CHB_USER_AGENT

        if CHB_CF_CLEARANCE:
            self.session.cookies.set(
                "cf_clearance",
                CHB_CF_CLEARANCE,
                domain=".chaturbate.com",
                path="/",
            )

    def getWebsiteURL(self):
        return "https://www.chaturbate.com/" + self.username

    def getVideoUrl(self):
        if self.bulk_update:
            self.getStatus()
        url = self.lastInfo["url"]
        if not url:
            return None
        if self.lastInfo.get("cmaf_edge"):
            url = url.replace("playlist.m3u8", "playlist_sfm4s.m3u8")
            url = re.sub("live-.+amlst", "live-c-fhls/amlst", url)

        return self.getWantedResolutionPlaylist(url)

    @staticmethod
    def _parseStatus(status):
        if status == "public":
            return Status.PUBLIC
        elif status in ["private", "hidden"]:
            return Status.PRIVATE
        else:
            return Status.OFFLINE

    def _log_proxy_test(self):
        if self._proxy_test_logged:
            return

        self._proxy_test_logged = True
        try:
            r = self.session.get(CHB_PROXY_TEST_URL, timeout=10)
            self.logger.info(
                "Chaturbate proxy test: proxies=%s user-agent=%s cf_clearance=%s status=%s body=%s",
                self.session.proxies,
                self.session.headers.get("User-Agent"),
                bool(self.session.cookies.get("cf_clearance")),
                r.status_code,
                r.text[:500],
            )
        except Exception as e:
            self.logger.info(
                "Chaturbate proxy test failed: proxies=%s user-agent=%s cf_clearance=%s error=%s",
                self.session.proxies,
                self.session.headers.get("User-Agent"),
                bool(self.session.cookies.get("cf_clearance")),
                e,
            )

    def getStatus(self):
        headers = {"X-Requested-With": "XMLHttpRequest"}
        data = {"room_slug": self.username, "bandwidth": "high"}

        try:
            self._log_proxy_test()
            r = self.session.post(
                "https://chaturbate.com/get_edge_hls_url_ajax/",
                headers=headers,
                data=data,
            )
            self.logger.info(
                "get_edge_hls_url_ajax response: status=%s content-type=%s body=%s",
                r.status_code,
                r.headers.get("Content-Type"),
                r.text[:1000],
            )
            self.lastInfo = r.json()
            status = self._parseStatus(self.lastInfo["room_status"])
            if status == status.PUBLIC and not self.lastInfo["url"]:
                status = status.RESTRICTED
        except Exception:
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
        if REQUESTS_PROXIES:
            session.proxies.update(REQUESTS_PROXIES)
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
