"""Live-model discovery helpers for the end-to-end recording tests.

The production bots only know how to look up a *given* model.  These helpers
answer the other half of the question: which model is live right now, so the
test can hand a real username to the bot and exercise its public recording
path.

Every helper talks to the same public discovery endpoints the sites use in a
browser.  They deliberately return a list of candidates instead of asserting
that one is live: a candidate can disappear between discovery and the bot's
own status request.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Callable
from urllib.parse import quote

from curl_cffi import requests as curl_requests


@dataclass(frozen=True)
class LiveCandidate:
    username: str
    room_id: str | None = None


class DiscoveryError(RuntimeError):
    """Discovery could not be attempted for this site."""


def _session() -> curl_requests.Session:
    return curl_requests.Session(impersonate="chrome")


def _get(session: curl_requests.Session, url: str, **kwargs):
    response = session.get(url, timeout=30, **kwargs)
    response.raise_for_status()
    return response


def _json(session: curl_requests.Session, url: str, **kwargs):
    return _get(session, url, **kwargs).json()


def _unique(values):
    return list(dict.fromkeys(value for value in values if value))


# Paths which show up as one-segment links on a model directory page but are
# not model names.  Anything not in this set is still just a candidate: the
# bot's own status call is the final word.
_NON_MODEL_PATHS = {
    "2257", "about", "advertising", "affiliates", "all", "all-models", "anal",
    "arab", "asian", "blog", "buzz", "cam4", "categories", "contact",
    "countries", "couple", "couples", "dmca", "faq", "feed", "female",
    "following", "gold", "help", "home", "how-to-play", "legal", "login",
    "male", "men", "models", "new", "niches", "privacy", "privates",
    "search", "signup", "support", "tags", "terms", "token", "training",
    "trans", "transgender", "women",
}


def _discover_amateur_tv() -> list[LiveCandidate]:
    session = _session()
    html = _get(session, "https://www.amateur.tv/").text
    usernames = re.findall(r'href="/([^"/?#]+)"', html)
    return [
        LiveCandidate(username)
        for username in _unique(usernames)
        if username not in _NON_MODEL_PATHS
        and not username.startswith(("section/", "tag/", "web/", "users/", "rankings/"))
    ]


def _discover_bongacams() -> list[LiveCandidate]:
    session = _session()
    html = _get(session, "https://bongacams.com/").text
    usernames = re.findall(r'href="/profile/([A-Za-z0-9_.-]+)"', html)
    return [LiveCandidate(username) for username in _unique(usernames)]


def _discover_cam4() -> list[LiveCandidate]:
    session = _session()
    html = _get(session, "https://hu.cam4.com/female/cams/online/hd").text
    usernames = re.findall(r'href="/([A-Za-z0-9_.-]+)"', html)
    # Prefer names that look like model handles (mixed case, digits or an
    # underscore) so the test does not spend its time probing static pages.
    def rank(username: str):
        looks_like_model = any(c.isupper() or c.isdigit() or c == "_" for c in username)
        return (not looks_like_model, username)

    return [
        LiveCandidate(username)
        for username in sorted(_unique(usernames), key=rank)
        if username not in _NON_MODEL_PATHS
    ]


def _discover_camscom() -> list[LiveCandidate]:
    session = _session()
    html = _get(session, "https://cams.com/").text
    match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not match:
        raise DiscoveryError("cams.com did not contain __NEXT_DATA__")
    data = json.loads(match.group(1))
    won = data["props"]["pageProps"]["initialData"]["wonStore"]["compressedWonResponse"]
    mapping = won["mapping"]
    if "screen_name" not in mapping:
        raise DiscoveryError("cams.com model mapping has no screen_name")
    index = mapping.index("screen_name")
    return [LiveCandidate(row[index]) for row in won.get("models", []) if row[index]]


def _discover_camsoda() -> list[LiveCandidate]:
    session = _session()
    data = _json(session, "https://www.camsoda.com/api/v1/browse/online?limit=25")
    candidates = []
    for result in data.get("results", []):
        template = result.get("tpl")
        if isinstance(template, dict) and template.get("1"):
            candidates.append(LiveCandidate(str(template["1"])))
    return _unique_candidates(candidates)


def _unique_candidates(candidates):
    seen = set()
    result = []
    for candidate in candidates:
        if candidate.username not in seen:
            seen.add(candidate.username)
            result.append(candidate)
    return result


def _discover_chaturbate() -> list[LiveCandidate]:
    session = _session()
    data = _json(
        session,
        "https://chaturbate.com/api/ts/roomlist/room-list/"
        "?enable_recommendations=false&limit=25&offset=0",
    )
    return [
        LiveCandidate(room["username"])
        for room in data.get("rooms", [])
        if room.get("username") and room.get("current_show") == "public"
    ]


def _discover_dreamcam(stream_type: str) -> list[LiveCandidate]:
    session = _session()
    url = (
        "https://bss.dreamcamtrue.com/api/clients/v1/broadcasts"
        f"?partnerId=dreamcam_oauth2&limit=25&offset=0&show-offline=false"
        f"&status=public&stream-types={stream_type}"
    )
    last_error = None
    for _ in range(3):
        try:
            data = _json(session, url)
            break
        except Exception as error:  # noqa: BLE001 - the API is occasionally slow
            last_error = error
    else:
        raise DiscoveryError(f"DreamCam discovery failed: {last_error}")

    candidates = []
    for item in data.get("pageItems", []):
        username = item.get("modelNickname")
        online = any(
            stream.get("streamType") == stream_type and stream.get("status") == "online"
            for stream in item.get("streams", [])
        )
        if username and online:
            candidates.append(LiveCandidate(username))
    return candidates


def _discover_dreamcam_2d() -> list[LiveCandidate]:
    return _discover_dreamcam("video2D")


def _discover_dreamcam_3d() -> list[LiveCandidate]:
    return _discover_dreamcam("video3D")


def _discover_fansly() -> list[LiveCandidate]:
    session = _session()
    data = _json(
        session,
        "https://apiv3.fansly.com/api/v1/contentdiscovery/livesuggestions"
        "?limit=20&ngsw-bypass=true",
    )
    candidates = []
    for account in data.get("response", {}).get("accounts", []):
        channel = (account.get("streaming") or {}).get("channel") or {}
        stream = channel.get("stream") or {}
        if account.get("username") and stream.get("status") == 2:
            candidates.append(LiveCandidate(account["username"], account.get("id")))
    return candidates


def _discover_manyvids() -> list[LiveCandidate]:
    session = _session()
    headers = {
        "Referer": "https://www.manyvids.com/live/online",
        "Origin": "https://www.manyvids.com",
    }
    candidates: list[LiveCandidate] = []
    next_token = None
    # The creators API is cursor-paginated.  One page of 300 is normally enough;
    # follow a couple of cursors so a quiet night still has candidates.
    for _ in range(3):
        url = "https://api.manyvids.com/live/creators?sortBy=rank&limit=300&status=online"
        if next_token:
            url += "&next_token=" + quote(str(next_token), safe="")
        data = _json(session, url, headers=headers)
        for creator in data.get("creators", []):
            if (
                creator.get("live_status") == "ONLINE"
                and creator.get("session_type") == "PUBLIC"
                and creator.get("url_handle")
            ):
                candidates.append(LiveCandidate(
                    creator["url_handle"], str(creator.get("user_id")) or None))
        next_token = data.get("next_token")
        if not next_token:
            break
    return _unique_candidates(candidates)


def _discover_myfreecams() -> list[LiveCandidate]:
    session = _session()
    data = _json(
        session,
        "https://api-edge.myfreecams.com/newsfeed"
        "?view_selection=all_models&size=25&page=0&offset=0&online_only=1",
    )
    users = data.get("result", {}).get("users", {})
    users_by_name = {
        user["username"]: user
        for user in users.values()
        if user.get("username") and user.get("online") == 1
    }
    candidates = [LiveCandidate(username) for username in users_by_name]
    candidates.sort(
        key=lambda candidate: -(users_by_name[candidate.username].get("cam_score") or 0)
    )
    return candidates


def _discover_streamate() -> list[LiveCandidate]:
    session = _session()
    data = _json(
        session,
        "https://streamate.com/v4/performers/fallback?domain=streamate.com",
    )
    return [
        LiveCandidate(performer["nickname"])
        for performer in data.get("performers", [])
        if performer.get("nickname")
    ]


def _discover_stripchat(vr_only: bool) -> list[LiveCandidate]:
    session = _session()
    data = _json(
        session,
        "https://stripchat.com/api/front/v2/models?limit=50&offset=0&primaryTag=girls",
    )
    candidates = []
    for block in data.get("blocks", []):
        for model in block.get("models", []):
            if (
                model.get("username")
                and model.get("status") == "public"
                and model.get("isOnline")
                and (not vr_only or model.get("isVr"))
            ):
                candidates.append(LiveCandidate(model["username"], str(model.get("id"))))
    return candidates


def _discover_stripchat_2d() -> list[LiveCandidate]:
    return _discover_stripchat(vr_only=False)


def _discover_stripchat_vr() -> list[LiveCandidate]:
    return _discover_stripchat(vr_only=True)


def _unsupported(reason: str) -> Callable[[], list[LiveCandidate]]:
    def discover():
        raise DiscoveryError(reason)

    return discover


DISCOVERERS: dict[str, Callable[[], list[LiveCandidate]]] = {
    "ATV": _discover_amateur_tv,
    "BC": _discover_bongacams,
    "C4": _discover_cam4,
    "CC": _discover_camscom,
    "CS": _discover_camsoda,
    "CB": _discover_chaturbate,
    "DC": _discover_dreamcam_2d,
    "DCVR": _discover_dreamcam_3d,
    "FL": _discover_fansly,
    "MV": _discover_manyvids,
    "MFC": _discover_myfreecams,
    "SM": _discover_streamate,
    "SC": _discover_stripchat_2d,
    "SCVR": _discover_stripchat_vr,
    "F4F": _unsupported(
        "Flirt4Free live-model discovery is not implemented; set "
        "STRMNTR_E2E_MODEL_F4F to a known model to test it"
    ),
    "SCHU": _unsupported(
        "SexChat.hu live-model discovery is not implemented; set "
        "STRMNTR_E2E_MODEL_SCHU to a known model to test it"
    ),
    "XLC": _unsupported(
        "XLoveCam live-model discovery is not implemented; set "
        "STRMNTR_E2E_MODEL_XLC to a known model to test it"
    ),
}


def discover(siteslug: str) -> tuple[list[LiveCandidate], str | None]:
    """Return candidates and an optional note about how they were found.

    ``STRMNTR_E2E_MODEL_<SLUG>`` and ``STRMNTR_E2E_ROOM_ID_<SLUG>`` let a
    developer pin a specific model when a site's discovery endpoint changes.
    """
    override = os.environ.get(f"STRMNTR_E2E_MODEL_{siteslug}")
    if override:
        room_id = os.environ.get(f"STRMNTR_E2E_ROOM_ID_{siteslug}")
        return [LiveCandidate(override, room_id)], "model from environment override"

    discoverer = DISCOVERERS.get(siteslug)
    if discoverer is None:
        raise DiscoveryError(f"no live-model discovery is implemented for {siteslug}")
    return discoverer(), None
