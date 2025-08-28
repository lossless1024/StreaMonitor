import m3u8
import os
import requests
import subprocess
from threading import Thread
from ffmpy import FFmpeg, FFRuntimeError
from time import sleep
from parameters import DEBUG, CONTAINER, SEGMENT_TIME, FFMPEG_PATH
import base64
import hashlib
from typing import Dict


class Decryptor:
    _cached_hash: Dict[str, bytes] = {}

    @classmethod
    def _compute_hash(cls, key: str) -> bytes:
        if key not in cls._cached_hash:
            hash_obj = hashlib.sha256(key.encode("utf-8"))
            cls._cached_hash[key] = hash_obj.digest()
        return cls._cached_hash[key]

    @classmethod
    def _decode(cls, encrypted_b64: str, key: str) -> str:
        hash_bytes = cls._compute_hash(key)
        hash_len = len(hash_bytes)

        encrypted_data = base64.b64decode(encrypted_b64 + "==")

        decrypted_bytes = bytearray()
        for i, cipher_byte in enumerate(encrypted_data):
            key_byte = hash_bytes[i % hash_len]
            decrypted_byte = cipher_byte ^ key_byte
            decrypted_bytes.append(decrypted_byte)

        plaintext = decrypted_bytes.decode("utf-8")
        return plaintext


def getVideoStriptChatHLS(self, url, filename):
    self.stopDownloadFlag = False
    error = False
    tmpfilename = filename[: -len("." + CONTAINER)] + ".tmp.ts"

    def debug_(message):
        self.debug(message, filename + ".log")

    def execute():
        nonlocal error
        downloaded_list = []
        with open(tmpfilename, "wb") as outfile:
            did_download = False
            while not self.stopDownloadFlag:
                r = requests.get(
                    url,
                    params={
                        "psch": "v1",
                        "pkey": "Zokee2OhPh9kugh4",
                    },
                    headers=self.headers,
                    cookies=self.cookies,
                )
                content = r.content.decode("utf-8")
                decoded = []
                lines = content.splitlines()
                for idx, line in enumerate(lines):
                    if line.startswith("#EXT-X-MOUFLON:FILE:"):
                        dec = Decryptor._decode(line[20:], "Quean4cai9boJa5a")
                        decoded.append(lines[idx + 1].replace("media.mp4", dec))
                    else:
                        decoded.append(line)
                chunklist = m3u8.loads("\n".join(decoded))
                if len(chunklist.segments) == 0:
                    return
               
                for chunk in  chunklist.segment_map + chunklist.segments:
                    if chunk.uri in downloaded_list:
                        continue
                    did_download = True
                    downloaded_list.append(chunk.uri)
                    chunk_uri = chunk.uri
                    debug_("Downloading " + chunk_uri)
                    if not chunk_uri.startswith("https://"):
                        chunk_uri = (
                            "/".join(url.split(".m3u8")[0].split("/")[:-1])
                            + "/"
                            + chunk_uri
                        )
                    m = requests.get(
                        chunk_uri, headers=self.headers, cookies=self.cookies
                    )
                    if m.status_code != 200:
                        return
                    outfile.write(m.content)
                    if self.stopDownloadFlag:
                        return
                if not did_download:
                    sleep(10)

    def terminate():
        self.stopDownloadFlag = True

    process = Thread(target=execute)
    process.start()
    self.stopDownload = terminate
    process.join()
    self.stopDownload = None

    if error:
        return False

    # Post-processing
    try:
        stdout = (
            open(filename + ".postprocess_stdout.log", "w+")
            if DEBUG
            else subprocess.DEVNULL
        )
        stderr = (
            open(filename + ".postprocess_stderr.log", "w+")
            if DEBUG
            else subprocess.DEVNULL
        )
        output_str = "-c:a copy -c:v copy"
        if SEGMENT_TIME is not None:
            output_str += (
                f" -f segment -reset_timestamps 1 -segment_time {str(SEGMENT_TIME)}",
            )
            filename = filename[: -len("." + CONTAINER)] + "_%03d." + CONTAINER
        ff = FFmpeg(
            executable=FFMPEG_PATH,
            inputs={tmpfilename: None},
            outputs={filename: output_str},
        )
        ff.run(stdout=stdout, stderr=stderr)
        os.remove(tmpfilename)
    except FFRuntimeError as e:
        if e.exit_code and e.exit_code != 255:
            return False

    return True
