import requests
from streamonitor.bot import Bot


class Chaturbate(Bot):
    site = 'Chaturbate'
    siteslug = 'CB'

    def __init__(self, username):
        super().__init__(username)
        self.sleep_on_offline = 30
        self.sleep_on_error = 60
        self.session = requests.Session()

    def getWebsiteURL(self):
        return "https://www.chaturbate.com/" + self.username

    def getVideoUrl(self):
        if not self.lastInfo.get('url'):
            self.logger.error("No base URL available in lastInfo")
            return None

        base_url = self.lastInfo['url']
        self.logger.debug(f"Base URL from Chaturbate API: {base_url}")

        # Update path to live-c-fhls and use playlist_sfm4s.m3u8
        corrected_url = base_url.replace('live-hls', 'live-c-fhls').replace('playlist.m3u8', 'playlist_sfm4s.m3u8')
        self.logger.debug(f"Corrected URL: {corrected_url}")

        headers = {
            "X-Requested-With": "XMLHttpRequest",
            "User-Agent": self.headers["User-Agent"],
            "Referer": f"https://chaturbate.com/{self.username}/",
            "Accept": "*/*",
            "Origin": "https://chaturbate.com",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept-Language": "en-US,en;q=0.9"
        }

        # Test accessibility
        try:
            response = self.session.get(corrected_url, headers=headers, timeout=10)
            self.logger.debug(f"Request headers: {response.request.headers}")
            if response.status_code == 200:
                self.logger.info(f"Stream URL accessible: {corrected_url}")
                self.logger.debug(f"Stream content:\n{response.text}")
                return corrected_url
            else:
                self.logger.error(f"Stream URL fetch failed (status: {response.status_code})")
                self.logger.debug(f"Response content:\n{response.text}")
                return None
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error fetching stream URL: {str(e)}")
            return None

    def getStatus(self):
        headers = {
            "X-Requested-With": "XMLHttpRequest",
            "User-Agent": self.headers["User-Agent"],
            "Referer": f"https://chaturbate.com/{self.username}/",
            "Accept": "*/*",
            "Origin": "https://chaturbate.com",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept-Language": "en-US,en;q=0.9"
        }
        data = {"room_slug": self.username, "bandwidth": "high"}

        try:
            r = self.session.post("https://chaturbate.com/get_edge_hls_url_ajax/",
                                headers=headers,
                                data=data,
                                timeout=10)
            r.raise_for_status()
            self.lastInfo = r.json()
            self.logger.debug(f"API response: {self.lastInfo}")
            self.logger.debug(f"Cookies set: {self.session.cookies.get_dict()}")
            self.logger.debug(f"Response headers: {r.headers}")
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error getting status: {str(e)}")
            self.lastInfo = {"room_status": "offline", "url": ""}

        if self.lastInfo["room_status"] == "public":
            status = self.Status.PUBLIC
        elif self.lastInfo["room_status"] in ["private", "hidden"]:
            status = self.Status.PRIVATE
        else:
            status = self.Status.OFFLINE

        self.ratelimit = status == self.Status.RATELIMIT
        return status


Bot.loaded_sites.add(Chaturbate)
