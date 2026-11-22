# StreaMonitor
A Python3 application for monitoring and saving (mostly adult) live streams from various websites.

Inspired by [Recordurbate](https://github.com/oliverjrose99/Recordurbate)

## Supported sites
| Site name     | Abbreviation | Aliases                     | Quirks                 | Selectable resolution |
|---------------|--------------|-----------------------------|------------------------|-----------------------|
| Bongacams     | `BC`         |                             |                        | Yes                   |
| Cam4          | `C4`         |                             |                        | Yes                   |
| Cams.com      | `CC`         |                             |                        | Currently only 360p   |
| CamSoda       | `CS`         |                             |                        | Yes                   |
| Chaturbate    | `CB`         |                             |                        | Yes                   |
| DreamCam      | `DC`         |                             |                        | No                    |
| DreamCam VR   | `DCVR`       |                             | for VR videos          | No                    |
| FanslyLive    | `FL`         |                             |                        | Yes                   |
| Flirt4Free    | `F4F`        |                             |                        | Yes                   |
| ManyVids Live | `MV`         |                             |                        | Yes (high/low)         |
| MyFreeCams    | `MFC`        |                             |                        | Yes                   |
| SexChat.hu    | `SCHU`       |                             | use the id as username | No                    |
| StreaMate     | `SM`         | PornHubLive, PepperCams,... |                        | Yes                   |
| StripChat     | `SC`         | XHamsterLive,...            | Mouflon keys auto-cache| Yes                   |
| StripChat VR  | `SCVR`       |                             | for VR videos          | No                    |
| XLoveCam      | `XLC`        |                             |                        | No                    |

Currently not supported:
* Amateur.TV (They use Widevine now)
* ImLive (Too strict captcha protection for scraping)
* LiveJasmin (No nudity in free streams)

There are hundreds of clones of the sites above, you can read about them on [this site](https://adultwebcam.site/clone-sites-by-platform/).

## Requirements
* Python 3
  * Install packages listed in requirements.txt with pip.
* FFmpeg

## Usage

The application has the following interfaces:
* Console
* External console via ZeroMQ (sort of working)
* Web interface

#### Starting and console
Start the downloader (it does not fork yet)\
Automatically imports all streamers from the config file.
```
python3 Downloader.py
```

On the console you can use the following commands:
```
add <username> <site> - Add streamer to the list (also starts monitoring)
remove <username> [<site>] - Remove streamer from the list
fav <username> [<site>] - Mark a configured streamer as favorite
unfav <username> [<site>] - Remove favorite status
fav list - List favorite models
start <username> [<site>] - Start monitoring streamer
start * - Start all
stop <username> [<site>] - Stop monitoring
stop * - stop all
status - Status display 
status2 - A slightly more readable status table
quit - Clean exit (Pressing CTRL-C also behaves like this)
```
For the `username` input, you usually have to enter the username as represented in the original URL of the room. 
Some sites are case-sensitive.

For the `site` input, you can use either the full or the short format of the site name. (And it is case-insensitive)

#### "Remote" controller
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

#### Web interface

You can access the web interface on port 5000. 
If set password in parameters.py username is admin, password admin, empty password is also allowed.
When you set the WEBSERVER_HOST it is also accesible to from other computers in the network

## Download folders

By default, recordings are grouped by day:

```text
downloads/YYYY-MM-DD/model [SITE]/model-SITENAME.mkv
```

You can start with the original single-folder layout using:

```bash
python3 Downloader.py --sf
```

The layout can also be configured without the command flag:

```text
STRMNTR_DOWNLOAD_DIR=downloads
STRMNTR_DOWNLOAD_BY_DATE=True
STRMNTR_DOWNLOAD_DATE_FORMAT=%Y-%m-%d
```

Set `STRMNTR_DOWNLOAD_BY_DATE=False` to use the original layout. `--sf`
overrides the setting for that process.

Date folders are reused safely:

- Existing files and folders are never deleted or replaced automatically.
- Recording names are made unique if the same filename already exists.
- Each running bot keeps the same date folder for the whole process.
- A second instance of the program only creates or reuses the folder for the
  current day.

## Docker support

You can run this application in docker. I prefer docker-compose so I included an example docker-compose.yml file that you can use.
Simply start it in the folder with `docker-compose up`.

The image includes everything needed for the supported sites, with no extra
host setup.

## Configuration

You can set some parameters in the [parameters.py](parameters.py).

If a recording is interrupted (network error, stalled ffmpeg, expired stream URL), the next attempt continues in a part file and the parts are merged into a single video when the show ends. `STRMNTR_FFMPEG_STALL_TIMEOUT` (default `45` seconds, `0` disables it) stops ffmpeg when it stops producing output so the recording can resume.

## Recording behavior and format support

- MyFreeCams uses the `edgevideo` LL-HLS/CMAF playlist first and keeps the
  legacy HLS URL as fallback.
- Chaturbate and MyFreeCams can combine separate CMAF audio and video
  renditions through a temporary local master playlist.
- HLS playlists are checked for the selected resolution and available media
  before FFmpeg or the native HLS downloader starts.
- Interrupted shows continue with numbered `.part` files and are merged when
  the show ends or after a reconnection timeout.
- Temporary offline, private, unknown or error states allow 45 seconds for
  reconnection before a show is consolidated.
- The native HLS downloader creates missing output directories, uses request
  timeouts and supports segment URI resolution.

## StripChat Mouflon

StripChat playlists use Mouflon markers and obfuscated media URIs. The
application downloads the public MIT-licensed key cache maintained by
[kesamom/stripchat_mouflon](https://github.com/kesamom/stripchat_mouflon),
validates `pkey`/`pdkey` pairs and stores them locally in
`stripchat_mouflon_keys.json`.

Key refresh runs asynchronously in a background thread, is limited to a
once-daily refresh for normal startup, and falls back to the local cache if
the remote source or network is unavailable. Missing keys are not treated as
successful recordings and force a delayed retry rather than starting FFmpeg
with unusable URIs.

## Favorite models

Start normal monitoring with:

```bash
python3 Downloader.py
```

Start only models marked as favorites with:

```bash
python3 Downloader.py --favs
```

Favorite status is stored separately in `config.favorites.json`. The original
`config.json` structure and normal `add`/`remove` behavior remain unchanged.
The favorites file is regenerated from `config.json` when configurations
change, while preserving existing `favorite: true` values.
If `config.favorites.json` does not exist, `Downloader.py --favs` creates it
automatically from `config.json` with `favorite: false` for every model.
Valid manual edits are synchronized automatically by the running config
watcher; partial or invalid JSON is ignored until it becomes valid.

Example:

```json
[
  {
    "site": "StripChat",
    "username": "MIA_MILK99",
    "running": true,
    "favorite": true
  }
]
```

You can edit `favorite` directly in a text editor or use console/ZeroMQ
commands:

```text
fav MIA_MILK99 SC
unfav MIA_MILK99 SC
fav list
```

## Disclaimer

This program is only a proof of concept and education project, I don't encourage anybody to use it. \
Most (if not every) streamers disallow recording their shows. Please respect their wish. \
If you don't, and you record them despite this request, please don't ever publish or share any recordings. \
If you either record or share the recorded shows, you might be legally punished. \
Also, please don't use this tool for monetization in any way.
