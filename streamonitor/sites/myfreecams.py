import urllib.parse
import requests
from bs4 import BeautifulSoup
from streamonitor.bot import Bot


class MyFreeCams(Bot):
    site = 'MyFreeCams'
    siteslug = 'MFC'

    def __init__(self, username):
        super().__init__(username)
        self.attrs = {}

    def getVideoUrl(self):
        if 'data-campreview-mid' not in self.attrs:
            return None

        sid = self.attrs['data-campreview-sid']
        mid = 100000000 + int(self.attrs['data-campreview-mid'])
        a = 'a_' if self.attrs['data-is-webrtc'] == 'false' else ''
        return self.getBestSubPlaylist(f"https://edgevideo.myfreecams.com/hls/NxServer/{sid}/ngrp:mfc_{a}{mid}.f4v_mobile/playlist.m3u8")

    def getStatus(self):
        r = requests.get(f'https://share.myfreecams.com/{self.username}')
        if r.status_code != 200:
            return False
        doc = r.content
        startpos = doc.find(b'https://www.myfreecams.com/php/tracking.php?')
        endpos = doc.find(b'"', startpos)
        url = urllib.parse.urlparse(doc[startpos:endpos])
        qs = urllib.parse.parse_qs(url.query)
        if b'model_id' not in qs:
            return Bot.Status.NOTEXIST

        doc = BeautifulSoup(doc, 'html.parser')
        params = doc.find(class_='campreview')
        if params:
            self.attrs = params.attrs
            if self.getVideoUrl():
                return Bot.Status.PUBLIC
            else:
                return Bot.Status.PRIVATE
        else:
            return Bot.Status.OFFLINE


Bot.loaded_sites.add(MyFreeCams)
