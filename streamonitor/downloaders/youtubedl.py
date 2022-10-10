import youtube_dl


def getVideoYtdl(self, url):
    self.log("Started downloading show")
    ydl_opts = {
        'outtmpl': self.genOutFilename()[:-4] + '.%(ext)s',
        'quiet': True,
        'logger': self.logger,
        'progress_hooks': [self.progressInfo]
    }

    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        try:
            ydl.download([url])
        except:
            self.sc = self.Status.ERROR
            self.log("Error while downloading")
