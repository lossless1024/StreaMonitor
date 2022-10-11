import logging

import youtube_dl


def getVideoYtdl(self, url, filename):
    ydl_opts = {
        'outtmpl': filename[:-4] + '.%(ext)s',
        'quiet': False,
        'logger': self.logger
    }

    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        try:
            ydl.download([url])
        except:
            return False
    return True
