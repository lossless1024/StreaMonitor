# CamGirl-DL
A Python3 application for saving camgirls' streams from various websites.
Inspired by [Recordurbate](https://github.com/oliverjrose99/Recordurbate)
## Requirements
* Python 3
  * requests
  * pyzmq
  * terminaltables
* Youtube-dl
* FFmpeg

## Usage

Start the downloader (it does not fork yet)
Automatically imports all streamers from the config file.
```
python3 downloader.py
```

Add or remove a streamer to record (Also saves config file)
```
python3 controller.py add <username> <website>
python3 controller.py remove <username>
```

Start/stop recording streamers
```
python3 controller.py <start|stop> <username>
```

List the streamers in the config
```
python3 controller.py status
```

