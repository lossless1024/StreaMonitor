"""Agora web-gateway recorder worker.

This module joins an Agora channel the same way the web client does: it asks
Agora's transpond service for a gateway edge, joins over the JSON/WebSocket
gateway, negotiates WebRTC with aiortc, and subscribes to the publisher's
audio and video.  Decoded frames are encoded to H.264/AAC MP4 with PyAV.

It is deliberately a separate process.  WebRTC, codec and native library
    teardown can crash a process; keeping the worker out of the monitor means a
    crash only ends one recording.  The parent talks to it with JSON lines.

The token is read from a private temporary config file and is never printed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import secrets
import sys
import time
from fractions import Fraction
from typing import Optional

import av
import numpy as np
import requests
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.mediastreams import AudioStreamTrack, MediaStreamError, VideoStreamTrack
from websockets.asyncio.client import connect

from streamonitor.downloaders.agora import AgoraCredentials

_CHOOSE_HOSTS = (
    "webrtc2-ap-web-1.agora.io",
    "webrtc2-2.ap.sd-rtn.com",
    "webrtc2-ap-web-3.agora.io",
    "webrtc2-4.ap.sd-rtn.com",
)
_SDK_VERSION = "4.23.1"
_CODEC = "vp8"
_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
_MEDIA_TIMEOUT = 30.0
_VIDEO_START_TIMEOUT = 10.0


def _emit(event: str, **fields) -> None:
    payload = {"event": event}
    payload.update(fields)
    print(json.dumps(payload, separators=(",", ":")), flush=True)


def _warn(message: str) -> None:
    _emit("warning", message=message)


def _error(message: str, code: int = 0) -> None:
    _emit("error", message=message, code=code)


class AgoraGatewayError(RuntimeError):
    def __init__(self, message: str, code: int = 0):
        super().__init__(message)
        self.code = code


class _Gateway:
    """Small request/response and event layer over the Agora gateway socket."""

    def __init__(self, websocket):
        self.ws = websocket
        self.pending: dict[str, asyncio.Future] = {}
        self.events: asyncio.Queue = asyncio.Queue()
        self.closed = asyncio.Event()
        self._receive_task = asyncio.create_task(self._receive())

    async def _receive(self) -> None:
        try:
            async for raw in self.ws:
                try:
                    frame = json.loads(raw)
                except (TypeError, ValueError):
                    continue
                request_id = frame.get("_id")
                future = self.pending.get(request_id)
                if future is not None and not future.done():
                    future.set_result(frame)
                    continue
                kind = frame.get("_type")
                if kind:
                    await self.events.put((kind, frame.get("_message") or {}))
        except Exception:  # noqa: BLE001 - websocket close is normal
            pass
        finally:
            self.closed.set()
            for future in self.pending.values():
                if not future.done():
                    future.set_exception(AgoraGatewayError("gateway disconnected"))

    async def request(self, kind: str, message=None, timeout: float = 10.0):
        request_id = secrets.token_hex(4)
        frame = {"_id": request_id, "_type": kind}
        if message is not None:
            frame["_message"] = message
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self.pending[request_id] = future
        await self.ws.send(json.dumps(frame, separators=(",", ":")))
        try:
            response = await asyncio.wait_for(future, timeout)
        finally:
            self.pending.pop(request_id, None)
        if response.get("_result") != "success":
            details = response.get("_message") or {}
            if isinstance(details, dict):
                code = int(details.get("error_code") or details.get("code") or 0)
                text = details.get("error_message") or details.get("message") or kind
            else:
                code, text = 0, str(details)
            raise AgoraGatewayError(str(text), code)
        return response.get("_message") or {}

    async def ping_loop(self, session) -> None:
        failures = 0
        while not self.closed.is_set() and not session.stop_event.is_set():
            await asyncio.sleep(3)
            try:
                await self.request("ping", None, timeout=5)
                failures = 0
            except Exception:  # noqa: BLE001
                failures += 1
                if failures >= 4:
                    _warn("Agora gateway stopped answering pings")
                    session.stop_event.set()
                    return

    async def close(self) -> None:
        try:
            await self.request("leave", None, timeout=3)
        except Exception:  # noqa: BLE001
            pass
        try:
            await self.ws.close()
        except Exception:  # noqa: BLE001
            pass
        self._receive_task.cancel()
        try:
            await self._receive_task
        except Exception:  # noqa: BLE001
            pass


def _choose_server(credentials: AgoraCredentials, user_agent: str):
    body = {
        "appid": credentials.app_id,
        "client_ts": int(time.time() * 1000),
        "opid": secrets.randbelow(10**12),
        "sid": secrets.token_hex(16),
        "request_bodies": [
            {
                "uri": 22,
                "buffer": {
                    "cname": credentials.channel,
                    "detail": {"11": "GLOBAL", "17": "2", "22": "GLOBAL"},
                    "key": credentials.token or "",
                    "service_ids": [11, 26],
                    "uid": credentials.uid,
                },
            }
        ],
    }
    headers = {"User-Agent": user_agent}
    last_error = "no Agora gateway"
    for host in _CHOOSE_HOSTS:
        try:
            response = requests.post(
                f"https://{host}/api/v2/transpond/webrtc?v=2",
                files={"request": (None, json.dumps(body))},
                headers=headers,
                timeout=20,
            )
        except Exception as error:  # noqa: BLE001
            last_error = f"{host}: {type(error).__name__}"
            continue
        if response.status_code != 200:
            last_error = f"{host}: HTTP {response.status_code}"
            continue
        try:
            data = response.json()
        except ValueError:
            last_error = f"{host}: invalid JSON"
            continue

        gateway = None
        for item in data.get("response_body") or []:
            buffer = item.get("buffer") or {}
            if buffer.get("flag") == 4096:
                gateway = buffer
                break
        if not gateway or gateway.get("code") != 0:
            last_error = f"{host}: gateway code {gateway.get('code') if gateway else '?'}"
            continue
        edges = [
            edge for edge in gateway.get("edges_services") or []
            if edge.get("ip") and edge.get("port")
        ]
        if not edges:
            last_error = f"{host}: no gateway edge"
            continue

        detail = dict(gateway.get("detail") or {})
        detail.update(data.get("detail") or {})
        ap_response = {
            "code": gateway.get("code", 0),
            "server_ts": data.get("enter_ts"),
            "uid": gateway.get("uid"),
            "cid": gateway.get("cid"),
            "cname": gateway.get("cname"),
            "detail": detail,
            "flag": 4096,
            "opid": data.get("opid"),
            "cert": gateway.get("cert"),
        }
        return ap_response, edges, gateway.get("cert", "")
    raise AgoraGatewayError(last_error)


def _parse_media_sections(sdp: str):
    sections = []
    for block in re.split(r"(?=^m=)", sdp, flags=re.M):
        if not block.startswith("m="):
            continue
        lines = block.splitlines()
        kind = lines[0].split()[0][2:]
        mid = ufrag = pwd = fingerprint = setup = None
        codecs: dict[int, dict] = {}
        for line in lines[1:]:
            if line.startswith("a=mid:"):
                mid = line[6:].strip()
            elif line.startswith("a=ice-ufrag:"):
                ufrag = line[12:].strip()
            elif line.startswith("a=ice-pwd:"):
                pwd = line[10:].strip()
            elif line.startswith("a=fingerprint:") and fingerprint is None:
                fingerprint = line[14:].strip()
            elif line.startswith("a=setup:"):
                setup = line[8:].strip()
            elif line.startswith("a=rtpmap:"):
                left, right = line[9:].split(None, 1)
                parts = right.split("/")
                codecs[int(left)] = {
                    "name": parts[0],
                    "clock": int(parts[1]),
                    "channels": int(parts[2]) if len(parts) > 2 else 1,
                }
            elif line.startswith("a=fmtp:"):
                left, right = line[7:].split(None, 1)
                codec = codecs.setdefault(int(left), {})
                codec.setdefault("fmtp", {})
                for pair in right.split(";"):
                    if "=" in pair:
                        key, value = pair.split("=", 1)
                        codec["fmtp"][key.strip()] = value.strip()
            elif line.startswith("a=rtcp-fb:"):
                left, right = line[10:].split(None, 1)
                codec = codecs.setdefault(int(left), {})
                codec.setdefault("fb", []).append(right.strip())
        sections.append({
            "kind": kind,
            "mid": mid,
            "ufrag": ufrag,
            "pwd": pwd,
            "fingerprint": fingerprint,
            "setup": setup,
            "codecs": codecs,
        })
    return sections


def _build_local_ortc(offer_sdp: str):
    sections = _parse_media_sections(offer_sdp)
    audio = next(section for section in sections if section["kind"] == "audio")
    video = next(section for section in sections if section["kind"] == "video")
    fingerprint = audio["fingerprint"]
    if not fingerprint:
        raise AgoraGatewayError("local SDP has no DTLS fingerprint")
    algorithm, value = fingerprint.split(" ", 1)

    def codec_list(section, names, feedback):
        result = []
        for payload_type, codec in section["codecs"].items():
            if codec.get("name", "").lower() not in names:
                continue
            rtp_map = {
                "encodingName": "opus" if codec["name"].lower() == "opus" else codec["name"],
                "clockRate": codec["clock"],
            }
            if codec.get("channels", 1) > 1:
                rtp_map["encodingParameters"] = codec["channels"]
            result.append({
                "payloadType": payload_type,
                "rtpMap": rtp_map,
                "rtcpFeedbacks": [
                    ({"type": entry.split(" ", 1)[0], "parameter": entry.split(" ", 1)[1]}
                     if " " in entry else {"type": entry})
                    for entry in feedback
                ],
                "fmtp": {"parameters": codec.get("fmtp", {})},
            })
        return result

    empty = {"audioCodecs": [], "audioExtensions": [], "videoCodecs": [], "videoExtensions": []}
    return {
        "iceParameters": {"iceUfrag": audio["ufrag"], "icePwd": audio["pwd"]},
        "dtlsParameters": {
            "fingerprints": [{"hashFunction": algorithm, "fingerprint": value}]
        },
        "rtpCapabilities": {
            "send": empty,
            "recv": empty,
            "sendrecv": {
                "audioCodecs": codec_list(audio, {"opus"}, ["transport-cc", "nack"]),
                "audioExtensions": [],
                "videoCodecs": codec_list(
                    video, {"vp8", "h264"}, ["transport-cc", "nack", "nack pli", "ccm fir"]
                ),
                "videoExtensions": [],
            },
        },
        "version": "2",
    }


def _build_answer_sdp(offer_sdp: str, server_ortc: dict) -> str:
    sections = _parse_media_sections(offer_sdp)
    capability = server_ortc.get("rtpCapabilities") or {}
    send = capability.get("sendrecv") or capability.get("send") or {}
    ice = server_ortc.get("iceParameters") or {}
    fingerprints = (server_ortc.get("dtlsParameters") or {}).get("fingerprints") or []
    fingerprint = fingerprints[0] if fingerprints else {}
    setup = {"server": "passive", "client": "active"}.get(
        (server_ortc.get("dtlsParameters") or {}).get("role"), "active"
    )

    lines = [
        "v=0",
        "o=- 0 0 IN IP4 127.0.0.1",
        "s=AgoraGateway",
        "t=0 0",
        f"a=group:BUNDLE {' '.join(section['mid'] for section in sections)}",
        "a=ice-lite",
        "a=msid-semantic: WMS",
    ]
    for section in sections:
        kind = section["kind"]
        selected = []
        for codec in send.get(kind + "Codecs") or []:
            payload_type = codec.get("payloadType", -1)
            if payload_type in section["codecs"]:
                selected.append((payload_type, codec))
        if not selected:
            fallback = "opus" if kind == "audio" else "vp8"
            selected = [
                (payload_type, {"payloadType": payload_type, "rtpMap": codec})
                for payload_type, codec in section["codecs"].items()
                if codec.get("name", "").lower() == fallback
            ]
        payload_types = [str(payload_type) for payload_type, _ in selected]
        lines.append(f"m={kind} 9 UDP/TLS/RTP/SAVPF {' '.join(payload_types)}")
        lines.append("c=IN IP4 127.0.0.1")
        lines.append("a=rtcp:9 IN IP4 0.0.0.0")
        lines.append(f"a=ice-ufrag:{ice.get('iceUfrag')}")
        lines.append(f"a=ice-pwd:{ice.get('icePwd')}")
        lines.append(
            f"a=fingerprint:{fingerprint.get('algorithm') or fingerprint.get('hashFunction')} "
            f"{fingerprint.get('fingerprint')}"
        )
        lines.append(f"a=setup:{setup}")
        lines.append(f"a=mid:{section['mid']}")
        for candidate in ice.get("candidates") or []:
            lines.append(
                f"a=candidate:{candidate.get('foundation')} 1 {candidate.get('protocol')} "
                f"{candidate.get('priority')} {candidate.get('ip')} {candidate.get('port')} "
                f"typ {candidate.get('type')}"
            )
        lines.append("a=sendonly")
        lines.append("a=rtcp-mux")
        lines.append("a=rtcp-rsize")
        for payload_type, codec in selected:
            rtp_map = codec.get("rtpMap") or {}
            name = rtp_map.get("encodingName")
            clock = rtp_map.get("clockRate")
            channels = rtp_map.get("encodingParameters")
            suffix = f"/{channels}" if channels else ""
            lines.append(f"a=rtpmap:{payload_type} {name}/{clock}{suffix}")
            for feedback in codec.get("rtcpFeedbacks") or []:
                parameter = feedback.get("parameter")
                lines.append(
                    f"a=rtcp-fb:{payload_type} {feedback.get('type')}"
                    + (f" {parameter}" if parameter else "")
                )
            fmtp = (codec.get("fmtp") or {}).get("parameters") or {}
            if fmtp:
                lines.append(
                    f"a=fmtp:{payload_type} "
                    + ";".join(f"{key}={value}" for key, value in fmtp.items())
                )
            elif section["codecs"][payload_type].get("fmtp"):
                lines.append(
                    f"a=fmtp:{payload_type} "
                    + ";".join(
                        f"{key}={value}"
                        for key, value in section["codecs"][payload_type]["fmtp"].items()
                    )
                )
    return "\r\n".join(lines) + "\r\n"


class _Mp4Writer:
    """Encode decoded aiortc frames to a fragmented H.264/AAC MP4."""

    def __init__(self, output: str):
        self.output = output
        self.container = None
        self.video = None
        self.audio = None
        self.video_frame = 0
        self.audio_frame = 0
        self.video_last_pts = -1
        self.audio_last_pts = -1
        self.base_time: Optional[float] = None
        self._audio_buffer: Optional[np.ndarray] = None
        self._audio_next_pts: Optional[int] = None
        self.recording = False

    def start(self, width: int, height: int, with_video: bool, with_audio: bool) -> None:
        if self.container is not None:
            return
        self.container = av.open(
            self.output, mode="w", format="mp4",
            options={"movflags": "frag_keyframe+empty_moov"},
        )
        if with_video:
            self.video = self.container.add_stream("libx264", rate=30)
            self.video.width = width or 1280
            self.video.height = height or 720
            self.video.pix_fmt = "yuv420p"
            self.video.time_base = Fraction(1, 30)
            self.video.options = {
                "preset": "veryfast",
                "tune": "zerolatency",
                "g": "60",
                "keyint_min": "30",
                "sc_threshold": "0",
            }
        if with_audio:
            self.audio = self.container.add_stream("aac", rate=48000)
            self.audio.layout = "stereo"
            self.audio.format = "fltp"
            self.audio.time_base = Fraction(1, 48000)

    def _time(self, frame) -> Optional[float]:
        value = getattr(frame, "time", None)
        return float(value) if value is not None else None

    def _pts(self, kind: str, frame, rate: int) -> int:
        now = self._time(frame)
        if now is not None:
            if self.base_time is None or now < self.base_time:
                self.base_time = now
            pts = int(round((now - self.base_time) * rate))
        elif kind == "video":
            pts = self.video_frame * rate // 30
        else:
            pts = self.audio_frame
        last = self.video_last_pts if kind == "video" else self.audio_last_pts
        if pts <= last:
            pts = last + 1
        if kind == "video":
            self.video_last_pts = pts
        else:
            self.audio_last_pts = pts
        return pts

    def _mux(self, packets) -> None:
        for packet in packets:
            self.container.mux(packet)
            self.recording = True

    def write_video(self, frame) -> None:
        if self.video is None:
            return
        array = frame.to_ndarray(format="yuv420p")
        av_frame = av.VideoFrame.from_ndarray(array, format="yuv420p")
        av_frame.pts = self._pts("video", frame, 30)
        av_frame.time_base = Fraction(1, 30)
        self._mux(self.video.encode(av_frame))
        self.video_frame += 1

    def write_audio(self, frame) -> None:
        if self.audio is None:
            return
        array = frame.to_ndarray()
        channels = len(getattr(frame.layout, "channels", ()) or ())
        if array.ndim != 2:
            return
        if getattr(frame.format, "name", "") == "s16":
            if array.shape[0] != 1:
                return
            if channels <= 0:
                channels = 2
            planar = array.reshape(-1, channels).T.astype(np.float32) / 32768.0
        else:
            planar = array.astype(np.float32)
            if planar.shape[0] == 1 and channels > 1:
                planar = np.repeat(planar, channels, axis=0)
        if planar.shape[0] == 1:
            planar = np.repeat(planar, 2, axis=0)
        elif planar.shape[0] > 2:
            planar = planar[:2]
        planar = np.ascontiguousarray(planar, dtype=np.float32)

        if self._audio_buffer is None:
            self._audio_buffer = planar.copy()
        else:
            self._audio_buffer = np.ascontiguousarray(
                np.concatenate((self._audio_buffer, planar), axis=1)
            )
        if self._audio_next_pts is None:
            now = self._time(frame)
            if now is not None:
                if self.base_time is None:
                    self.base_time = now
                self._audio_next_pts = max(
                    0, int(round((now - self.base_time) * 48000))
                )
            else:
                self._audio_next_pts = max(0, self.audio_last_pts + 1)

        # AAC wants 1024 samples per frame, while Opus delivers 960 (20 ms).
        # Keep a small PCM FIFO and emit exact AAC frames.
        frame_size = self.audio.frame_size or 1024
        while self._audio_buffer.shape[1] >= frame_size:
            chunk = np.ascontiguousarray(
                self._audio_buffer[:, :frame_size], dtype=np.float32
            )
            av_frame = av.AudioFrame.from_ndarray(
                chunk, format="fltp", layout="stereo"
            )
            av_frame.sample_rate = 48000
            av_frame.time_base = Fraction(1, 48000)
            av_frame.pts = self._audio_next_pts
            self._mux(self.audio.encode(av_frame))
            self._audio_next_pts += frame_size
            self.audio_last_pts = av_frame.pts
            self.audio_frame += av_frame.samples
            self._audio_buffer = np.ascontiguousarray(
                self._audio_buffer[:, frame_size:], dtype=np.float32
            )

    def close(self) -> None:
        if self.container is None:
            return
        if self.audio is not None and self._audio_buffer is not None:
            frame_size = self.audio.frame_size or 1024
            remaining = self._audio_buffer.shape[1]
            if remaining:
                padded = np.zeros((2, frame_size), dtype=np.float32)
                padded[:, :remaining] = self._audio_buffer
                av_frame = av.AudioFrame.from_ndarray(
                    np.ascontiguousarray(padded), format="fltp", layout="stereo"
                )
                av_frame.sample_rate = 48000
                av_frame.time_base = Fraction(1, 48000)
                av_frame.pts = self._audio_next_pts or 0
                self._mux(self.audio.encode(av_frame))
            self._audio_buffer = None
        for stream in (self.video, self.audio):
            if stream is not None:
                self._mux(stream.encode(None))
        self.container.close()
        self.container = None


class _Session:
    def __init__(self, config: dict):
        self.config = config
        self.output = config["output"]
        self.user_agent = config.get("userAgent") or _DEFAULT_UA
        self.preferred_stream = config.get("streamType") or "high"
        self.max_duration = max(0, int(config.get("maxDurationSec") or 0))
        self.stop_event = asyncio.Event()
        self.gateway: Optional[_Gateway] = None
        self.pc: Optional[RTCPeerConnection] = None
        self.writer = _Mp4Writer(self.output)
        self.media_seen = False
        self.media_started = 0.0
        self._media_sent = False
        self._video_seen = False
        self._audio_seen = False
        self._tasks: list[asyncio.Task] = []
        self._writer_task: Optional[asyncio.Task] = None
        self._token = config.get("token") or ""

    def renew_token(self, token: str) -> None:
        # The current gateway session keeps its original token; the newest token
        # is used if the worker has to reconnect.  ManyVids tokens last 24h and
        # a recording rarely spans an expiry boundary.
        self._token = token

    def _emit_media(self, width, height, video, audio) -> None:
        if self._media_sent:
            return
        self._media_sent = True
        _emit("media", width=width, height=height, video=video, audio=audio)

    def _media_event(self, frame, kind: str) -> None:
        if not self.media_seen:
            self.media_seen = True
            self.media_started = time.monotonic()
        if kind == "video" and not self._video_seen:
            self._video_seen = True
            self._emit_media(frame.width, frame.height, "vp8", "opus")
        elif kind == "audio":
            self._audio_seen = True

    async def _subscribe_events(self) -> None:
        assert self.gateway is not None
        subscribed = set()
        while not self.stop_event.is_set() and not self.gateway.closed.is_set():
            try:
                kind, event = await asyncio.wait_for(self.gateway.events.get(), 0.5)
            except asyncio.TimeoutError:
                continue
            if kind not in ("on_add_video_stream", "on_add_audio_stream"):
                if kind in ("on_user_offline", "on_remove_stream"):
                    await asyncio.sleep(2)
                    if not self.stop_event.is_set():
                        self.stop_event.set()
                continue
            stream_type = "video" if kind.endswith("video_stream") else "audio"
            key = (stream_type, event.get("uid"), event.get("ssrcId"))
            if key in subscribed:
                continue
            subscribed.add(key)
            subscribe = {
                "stream_id": event.get("uid"),
                "stream_type": stream_type,
                "mode": "live",
                "codec": _CODEC,
                "p2p_id": 1,
                "twcc": False,
                "rtx": False,
                "extend": "",
                "ssrcId": event.get("ssrcId"),
            }
            try:
                await self.gateway.request("subscribe", subscribe, timeout=10)
            except Exception as error:  # noqa: BLE001
                _warn(f"could not subscribe to {stream_type}: {error}")

    async def _read_track(self, track) -> None:
        kind = track.kind
        while not self.stop_event.is_set():
            try:
                frame = await asyncio.wait_for(track.recv(), 1.0)
            except asyncio.TimeoutError:
                if not self.media_seen and time.monotonic() - self.media_started > _MEDIA_TIMEOUT:
                    _error("Agora recorder received no media", 10)
                    self.stop_event.set()
                    return
                continue
            except MediaStreamError:
                if not self.stop_event.is_set():
                    _warn(f"Agora {kind} track ended")
                    self.stop_event.set()
                return
            self._media_event(frame, kind)
            self._enqueue(kind, frame)

    def _enqueue(self, kind: str, frame) -> None:
        # The writer pulls frames; a bounded queue drops old video if encoding
        # falls behind, which is preferable to unbounded memory growth.
        if self._media_queue.full():
            try:
                self._media_queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        self._media_queue.put_nowait((kind, frame))

    async def _write_media(self) -> None:
        try:
            await self._write_media_loop()
        except Exception as error:  # noqa: BLE001 - a bad frame must not kill the worker
            _error(f"Agora writer failed: {type(error).__name__}: {error}")
            self.stop_event.set()

    async def _write_media_loop(self) -> None:
        buffered: list[tuple[str, object]] = []
        started = False
        deadline = time.monotonic() + _VIDEO_START_TIMEOUT
        while not self.stop_event.is_set() or not self._media_queue.empty():
            try:
                kind, frame = await asyncio.wait_for(self._media_queue.get(), 0.5)
            except asyncio.TimeoutError:
                if not started and time.monotonic() >= deadline:
                    # Audio-only or a publisher that never sends video.
                    if buffered:
                        self._emit_media(None, None, None, "opus")
                        self.writer.start(0, 0, False, True)
                        started = True
                        for item_kind, item_frame in buffered:
                            if item_kind == "audio":
                                self.writer.write_audio(item_frame)
                        buffered.clear()
                        self._recording()
                continue
            if not started:
                if kind == "video":
                    width, height = frame.width, frame.height
                    self._emit_media(width, height, "vp8", "opus")
                    self.writer.start(width, height, True, True)
                    started = True
                    for item_kind, item_frame in buffered:
                        if item_kind == "video":
                            self.writer.write_video(item_frame)
                        else:
                            self.writer.write_audio(item_frame)
                    buffered.clear()
                    self.writer.write_video(frame)
                    self._recording()
                else:
                    buffered.append((kind, frame))
                    if len(buffered) > 500:
                        buffered.pop(0)
                continue
            if kind == "video":
                self.writer.write_video(frame)
            else:
                self.writer.write_audio(frame)
            if self.writer.recording:
                self._recording()

    def _recording(self) -> None:
        if not self._recording_sent:
            self._recording_sent = True
            _emit("recording", file=self.output)

    async def _run(self) -> int:
        uid = self.config["uid"]
        try:
            uid = int(uid)
        except (TypeError, ValueError):
            pass
        credentials = AgoraCredentials(
            app_id=self.config["appId"],
            channel=self.config["channel"],
            token=self.config.get("token") or "",
            uid=uid,
        )
        loop = asyncio.get_running_loop()
        self.media_started = time.monotonic()
        ap_response, edges, cert = await loop.run_in_executor(
            None, _choose_server, credentials, self.user_agent
        )
        edge = edges[0]
        uri = (
            f"wss://{edge['ip'].replace('.', '-')}.edge.agora.io:{int(edge['port'])}"
        )
        ws = await connect(
            uri,
            additional_headers={"User-Agent": self.user_agent},
            max_size=None,
            ping_interval=None,
        )
        self.gateway = _Gateway(ws)
        self._tasks.append(asyncio.create_task(self._subscribe_events()))
        self._tasks.append(asyncio.create_task(self.gateway.ping_loop(self)))

        self.pc = RTCPeerConnection()
        self.pc.addTrack(AudioStreamTrack())
        self.pc.addTrack(VideoStreamTrack())
        offer = await self.pc.createOffer()
        await self.pc.setLocalDescription(offer)
        ortc = _build_local_ortc(offer.sdp)

        session_id = secrets.token_hex(16).upper()
        join = {
            "p2p_id": 1,
            "session_id": session_id,
            "app_id": credentials.app_id,
            "channel_key": credentials.token or "",
            "channel_name": credentials.channel,
            "sdk_version": _SDK_VERSION,
            "browser": self.user_agent,
            "process_id": "process-" + secrets.token_hex(16),
            "mode": "live",
            "codec": _CODEC,
            "role": "audience",
            "has_changed_gateway": False,
            "ap_response": {**ap_response, "ticket": cert},
            "extend": "",
            "details": {},
            "features": {"rejoin": True},
            "attributes": {
                "userAttributes": {
                    "enablePublishedUserList": True,
                    "maxSubscription": 50,
                }
            },
            "join_ts": int(time.time() * 1000),
            "ortc": ortc,
        }
        try:
            message = await self.gateway.request("join_v3", join, timeout=20)
        except Exception as error:  # noqa: BLE001
            code = getattr(error, "code", 0)
            _error(f"Agora join failed: {error}", code)
            return 1
        server_ortc = message.get("ortc")
        if not server_ortc:
            _error("Agora join returned no session description", 11)
            return 1
        answer = _build_answer_sdp(offer.sdp, server_ortc)
        await self.pc.setRemoteDescription(RTCSessionDescription(sdp=answer, type="answer"))
        _emit("joined")

        self._media_queue: asyncio.Queue = asyncio.Queue(maxsize=300)
        self._recording_sent = False
        writers = []
        for receiver in self.pc.getReceivers():
            writers.append(asyncio.create_task(self._read_track(receiver.track)))
        writer_task = asyncio.create_task(self._write_media())
        self._writer_task = writer_task
        self._tasks.extend(writers)
        self._tasks.append(writer_task)

        if self.max_duration:
            loop.call_later(self.max_duration, self.stop_event.set)

        self.pc.on("connectionstatechange", self._connection_changed)

        await self.stop_event.wait()
        return 0

    def _connection_changed(self) -> None:
        if self.pc is not None and self.pc.connectionState in ("failed", "closed"):
            self.stop_event.set()

    async def run(self) -> int:
        try:
            code = await self._run()
        except Exception as error:  # noqa: BLE001 - report and exit cleanly
            _error(f"Agora recorder failed: {error}")
            code = 1
        finally:
            await self._shutdown()
        return code

    async def _shutdown(self) -> None:
        self.stop_event.set()
        writer_task = self._writer_task
        for task in self._tasks:
            if task is not writer_task:
                task.cancel()
        await asyncio.gather(
            *(task for task in self._tasks if task is not writer_task),
            return_exceptions=True,
        )
        # Drain frames already received before closing the muxer.  Cancelling
        # the writer immediately would throw away up to several seconds at the
        # end of every recording.
        if writer_task is not None and not writer_task.done():
            try:
                await asyncio.wait_for(writer_task, 15)
            except Exception:  # noqa: BLE001 - a failed writer is already reported
                writer_task.cancel()
                await asyncio.gather(writer_task, return_exceptions=True)
        if self.pc is not None:
            try:
                await self.pc.close()
            except Exception:  # noqa: BLE001
                pass
        if self.gateway is not None:
            await self.gateway.close()
        self.writer.close()
        if self.writer.recording:
            _emit("stopped", file=self.output)


def _read_command(session: _Session, loop: asyncio.AbstractEventLoop) -> None:
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        if line in ("stop", "q", "1"):
            loop.call_soon_threadsafe(session.stop_event.set)
            return
        try:
            command = json.loads(line)
        except ValueError:
            continue
        if command.get("command") == "renew" and command.get("token"):
            session.renew_token(str(command["token"]))
        elif command.get("command") == "stop":
            loop.call_soon_threadsafe(session.stop_event.set)
            return


async def _run_config(config: dict) -> int:
    session = _Session(config)
    loop = asyncio.get_running_loop()
    import signal
    import threading

    for signum in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(signum, session.stop_event.set)
        except (NotImplementedError, RuntimeError):
            pass
    threading.Thread(
        target=_read_command, args=(session, loop), name="agora-worker-stdin", daemon=True
    ).start()
    return await session.run()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Agora WebRTC recorder worker")
    parser.add_argument("--config", required=True)
    args = parser.parse_args(argv)
    with open(args.config, "r", encoding="utf-8") as config_file:
        config = json.load(config_file)
    return asyncio.run(_run_config(config))


if __name__ == "__main__":
    raise SystemExit(main())
