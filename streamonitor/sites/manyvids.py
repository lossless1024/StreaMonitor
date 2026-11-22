"""ManyVids Live.

ManyVids moved from CloudFront HLS to Agora.  The site's public player resolves
a handle to a numeric user id, reads the room state from the live API and calls
``joinChannel`` to obtain Agora credentials.  All of that HTTP lives here; the
downloader only sees an :class:`AgoraStream`.
"""

import re
import time

import parameters
from streamonitor.downloaders.agora import AgoraBot, AgoraCredentials, AgoraStream
from streamonitor.enums import Status

_LIVE_URL = "https://www.manyvids.com/live/cam/{handle}"
_ROOM_URL = "https://api.manyvids.com/live/room/{user_id}"
_JOIN_URL = "https://api.manyvids.com/live/room/{user_id}/joinChannel"
_REFERER = "https://www.manyvids.com/live/online"
_ORIGIN = "https://www.manyvids.com"

_ROOM_ID_RE = re.compile(r'"roomId"\s*:\s*"(\d+)"')
_PROFILE_ID_RE = re.compile(r'"profileURL"\s*:\s*"/Profile/(\d+)/')

_ROOM_FIELDS = (
    "user_id",
    "room_state",
    "streaming_state",
    "creator_info",
    "private_config",
    "viewer_count",
)


class ManyVids(AgoraBot):
    site = "ManyVids"
    siteslug = "MV"

    # App ID used by the ManyVids player.  It is public and appears in every
    # player bundle; the channel/token/uid still come from joinChannel.
    APP_ID = "07af9cc5c9cd4cf7bf0b730a72997902"

    def __init__(self, username):
        self.user_id = username if username.isdigit() else None
        super().__init__(username)

    def getWebsiteURL(self):
        return _LIVE_URL.format(handle=self.username)

    def _headers(self, json_response=True):
        headers = dict(self.headers)
        headers.update({
            "Referer": _REFERER,
            "Origin": _ORIGIN,
        })
        if json_response:
            headers["Accept"] = "application/json, text/plain, */*"
        return headers

    def _resolve_user_id(self):
        """Return the numeric user id, or ``None`` when the handle is unknown."""
        if self.user_id:
            return self.user_id
        if self.username.isdigit():
            self.user_id = self.username
            return self.user_id

        response = self.session.get(
            _LIVE_URL.format(handle=self.username),
            headers=self._headers(json_response=False),
            timeout=30,
        )
        if response.status_code == 404:
            return None
        if response.status_code == 403:
            raise PermissionError("ManyVids denied access to the profile page")
        if response.status_code != 200:
            raise RuntimeError(f"ManyVids profile page returned {response.status_code}")

        match = _ROOM_ID_RE.search(response.text) or _PROFILE_ID_RE.search(response.text)
        if not match:
            # Newer player builds dropped the ``profileURL`` key; the link to
            # the requested handle still carries the numeric id.
            handle_pattern = re.compile(
                r"/Profile/(\d+)/" + re.escape(self.username) + r"(?:[/?#\"]|$)",
                re.IGNORECASE,
            )
            match = handle_pattern.search(response.text)
        if not match:
            raise RuntimeError(
                "ManyVids profile page did not contain the user id; the page "
                "layout may have changed"
            )
        self.user_id = match.group(1)
        self.logger.debug(f"Resolved ManyVids user id: {self.user_id}")
        return self.user_id

    def _get_room(self, user_id):
        return self.session.get(
            _ROOM_URL.format(user_id=user_id),
            headers=self._headers(),
            timeout=30,
        )

    def _safe_room_info(self, data):
        # Keep the interesting room state but never a token, even if the API
        # starts returning one in the room payload.
        if not isinstance(data, dict):
            return {}
        info = {key: data[key] for key in _ROOM_FIELDS if key in data}
        info.pop("token", None)
        info.pop("rtc", None)
        return info

    def getStatus(self):
        try:
            user_id = self._resolve_user_id()
        except PermissionError:
            return Status.RESTRICTED
        except Exception as error:  # noqa: BLE001 - network/API failures are retried
            self.logger.warning(f"Could not resolve ManyVids user id: {error}")
            return Status.UNKNOWN

        if user_id is None:
            return Status.NOTEXIST

        try:
            response = self._get_room(user_id)
        except Exception as error:  # noqa: BLE001
            self.logger.warning(f"ManyVids room request failed: {error}")
            return Status.UNKNOWN

        if response.status_code == 404:
            # The cached id may be stale after a handle change; resolve once more.
            self.user_id = None
            try:
                user_id = self._resolve_user_id()
            except Exception as error:  # noqa: BLE001
                self.logger.warning(f"Could not re-resolve ManyVids user id: {error}")
                return Status.UNKNOWN
            if user_id is None:
                return Status.NOTEXIST
            try:
                response = self._get_room(user_id)
            except Exception as error:  # noqa: BLE001
                self.logger.warning(f"ManyVids room request failed: {error}")
                return Status.UNKNOWN
        if response.status_code == 403:
            return Status.RESTRICTED
        if response.status_code == 429:
            return Status.RATELIMIT
        if response.status_code == 404:
            return Status.NOTEXIST
        if response.status_code != 200:
            return Status.UNKNOWN

        try:
            data = response.json()
        except Exception:  # noqa: BLE001 - an HTML challenge or error page
            self.logger.warning("ManyVids room response was not JSON")
            return Status.UNKNOWN

        self.lastInfo = self._safe_room_info(data)
        room_state = data.get("room_state")
        streaming_state = data.get("streaming_state")

        if streaming_state == "PRIVATE":
            return Status.PRIVATE
        if room_state == "ONLINE" and streaming_state == "PUBLIC":
            return Status.PUBLIC
        if room_state == "OFFLINE":
            return Status.OFFLINE
        return Status.UNKNOWN

    def _join_channel(self):
        """Call joinChannel and build the Agora credentials."""
        if not self.user_id:
            raise RuntimeError("ManyVids user id is not known yet")
        if self.lastInfo.get("streaming_state") != "PUBLIC":
            raise RuntimeError("ManyVids room is not public")

        response = self.session.post(
            _JOIN_URL.format(user_id=self.user_id),
            json={"visibility": "PUBLIC"},
            headers=self._headers(),
            timeout=30,
        )
        if response.status_code == 403:
            raise PermissionError("ManyVids joinChannel was forbidden")
        if response.status_code == 404:
            raise LookupError("ManyVids room no longer exists")
        if response.status_code == 429:
            raise RuntimeError("ManyVids joinChannel was rate limited")
        if response.status_code != 200:
            raise RuntimeError(f"ManyVids joinChannel returned {response.status_code}")

        data = response.json()
        meeting = data.get("meetingInfo") or {}
        channel = meeting.get("channelId")
        token = meeting.get("rtc")
        uid = meeting.get("uid")
        expires = meeting.get("expires")

        if not channel or not token or uid is None:
            raise RuntimeError("ManyVids joinChannel response is missing credentials")
        try:
            uid = int(uid)
        except (TypeError, ValueError) as error:
            raise RuntimeError("ManyVids joinChannel returned a non-numeric uid") from error

        expires_at = None
        try:
            expires_ms = int(expires)
            if expires_ms > 0:
                expires_at = time.time() + expires_ms / 1000
        except (TypeError, ValueError):
            pass

        return AgoraCredentials(
            app_id=self.APP_ID,
            channel=str(channel),
            token=str(token),
            uid=uid,
            expires_at=expires_at,
        )

    def getVideoUrl(self):
        if self.lastInfo.get("streaming_state") != "PUBLIC":
            self.logger.warning("Refusing to join a non-public ManyVids room")
            return None
        try:
            credentials = self._join_channel()
        except Exception as error:  # noqa: BLE001 - reported as a failed recording
            self.logger.warning(f"Could not join ManyVids channel: {error}")
            return None

        return AgoraStream(
            credentials=credentials,
            refresh=self._join_channel,
            referer=_REFERER,
            user_agent=self.headers.get("User-Agent"),
            label=f"ManyVids/{self.username}",
            preferred_stream=parameters.AGORA_STREAM_TYPE,
        )
