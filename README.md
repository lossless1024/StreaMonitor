# StreaMonitor
A Python3 application for monitoring and saving (mostly adult) live streams from various websites.

Inspired by [Recordurbate](https://github.com/oliverjrose99/Recordurbate)

## Supported sites
* Bongacams
* Chaturbate
* StreaMate (alias: PornHubLive, PepperCams,...)
* StripChat (alias: XHamsterLive,...)
* SexChat.hu
* CamSoda
* Cam4
* MyFreeCams

Planned to support:
* Cams.com
* Flirt4Free
* ImLive
* LiveJasmin

There are hundreds of clones of the sites above, you can read about them on [this site](https://adultwebcam.site/clone-sites-by-platform/).

## Requirements
* Python 3
  * requests
  * flask
  * youtube-dl
  * pyzmq
  * terminaltables
* FFmpeg

## Usage

Start the downloader (it does not fork yet)\
Automatically imports all streamers from the config file.
```
python3 Downloader.py
```

Add or remove a streamer to record (Also saves config file)
```
python3 Controller.py add <username> <website>
python3 Controller.py remove <username>
```

Start/stop recording streamers
```
python3 Controller.py <start|stop> <username>
```

List the streamers in the config
```
python3 Controller.py status
```

