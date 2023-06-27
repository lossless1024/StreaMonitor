# StreaMonitor
A Python application for monitoring and saving (mostly adult) live streams from various websites.

Inspired by: [Recordurbate](https://github.com/oliverjrose99/Recordurbate)
Thumbnail system code by: [VCSI](https://github.com/amietn/vcsi)

## Supported sites
| Site name      | Abbreviation | Aliases                     | Quirks                 | Selectable resolution |
|----------------|--------------|-----------------------------|------------------------|-----------------------|
| Bongacams      | `BC`         |                             |                        | Yes                   |
| Cam4           | `C4`         |                             |                        | Yes                   |
| Cams.com       | `CC`         |                             |                        | Currently only 360p   |
| CamSoda        | `CS`         |                             |                        | Yes                   |
| Chaturbate     | `CB`         |                             |                        | Yes                   |
| Cherry.TV      | `CHTV`       |                             |                        | Yes                   |
| Dreamcam VR    | `DCVR`       |                             |                        | No                    |
| Flirt4Free     | `F4F`        |                             |                        | Yes                   |
| ManyVids Live  | `MV`         |                             |                        | Yes                   |
| MyFreeCams     | `MFC`        |                             |                        | Yes                   |
| SexChat.hu     | `SCHU`       |                             | use the id as username | No                    |
| StreaMate      | `SM`         | PornHubLive, PepperCams,... |                        | Yes                   |
| StripChat      | `SC`         | XHamsterLive,...            |                        | Yes                   |
| StripChat VR   | `SCVR`       |                             | for VR videos          | No                    |

Currently not supported:
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
* Web interface (only status)

#### Starting and console
Start the downloader with the following command.
Automatically imports all streamers from the config file.
```
python Downloader.py
```
(On Windows you can use the `run.bat` file)

On the console you can use the following commands:
```
add <username> <site> - Add streamer to the list (also starts monitoring)
remove <username> [<site>] - Remove streamer from the list
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
It just prints the same information as the status command. 
You can also get a list of the recorded streams.

Further improvements can be expected.

## Docker support

You can run this application in docker. I prefer docker-compose so I included an example docker-compose.yml file that you can use.
Simply start it in the folder with `docker-compose up`.

## Configuration

You can set some parameters in the parameters.py.

## Disclaimer

This program is only a proof of concept and education project, I don't encourage anybody to use it. \
Most (if not every) streamers disallow recording their shows. Please respect their wish. \
If you don't, and you record them despite this request, please don't ever publish or share any recordings. \
If you either record or share the recorded shows, you might be legally punished. \
Also, please don't use this tool for monetization in any way.