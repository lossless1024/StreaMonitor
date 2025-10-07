import urllib.parse
import requests
from bs4 import BeautifulSoup
from streamonitor.bot import Bot
from streamonitor.enums import Status


class MyFreeCams(Bot):
    site = 'MyFreeCams'
    siteslug = 'MFC'

    def __init__(self, username):
        super().__init__(username)
        self.attrs = {}
        self.videoUrl = None

    def getWebsiteURL(self):
        return "https://www.myfreecams.com/#" + self.username

    def getVideoUrl(self, refresh=False):
        if not refresh:
            return self.videoUrl

        if 'data-cam-preview-model-id-value' not in self.attrs:
            return None

        sid = self.attrs['data-cam-preview-server-id-value']
        mid = 100000000 + int(self.attrs['data-cam-preview-model-id-value'])
        a = 'a_' if self.attrs['data-cam-preview-is-wzobs-value'] == 'true' else ''
        playlist_url = f"https://previews.myfreecams.com/hls/NxServer/{sid}/ngrp:mfc_{a}{mid}.f4v_mobile_mhp1080_previewurl/playlist.m3u8"
        r = requests.get(playlist_url)
        if r.status_code != 200:
            return None
        return self.getWantedResolutionPlaylist(playlist_url)

    def getStatus(self):
        r = requests.get(f'https://share.myfreecams.com/{self.username}')
        if r.status_code == 404:
            return Status.NOTEXIST
        if r.status_code != 200:
            return Status.UNKNOWN
        doc = r.content
        startpos = doc.find(b'https://www.myfreecams.com/php/tracking.php?')
        endpos = doc.find(b'"', startpos)
        url = urllib.parse.urlparse(doc[startpos:endpos])
        qs = urllib.parse.parse_qs(url.query)
        if b'model_id' not in qs:
            return Status.NOTEXIST

        doc = BeautifulSoup(doc, 'html.parser')
        params = doc.find(class_='campreview')
        if params:
            self.attrs = params.attrs
            self.videoUrl = self.getVideoUrl(refresh=True)
            if self.videoUrl:
                return Status.PUBLIC
            else:
                return Status.PRIVATE
        else:
            return Status.OFFLINE
