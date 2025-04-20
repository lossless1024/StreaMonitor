from flask import Flask, render_template, request, send_from_directory
import os
import json
import logging

from functools import wraps
from streamonitor.bot import Bot
import streamonitor.log as log
from streamonitor.manager import Manager
from streamonitor.managers.outofspace_detector import OOSDetector
from parameters import WEBSERVER_HOST, WEBSERVER_PORT, WEBSERVER_PASSWORD
from secrets import compare_digest


class HTTPManager(Manager):
    def __init__(self, streamers):
        super().__init__(streamers)
        self.logger = log.Logger("manager")
    
    def run(self):
        app = Flask(__name__, "", "../../web")
        werkzeug_logger = logging.getLogger('werkzeug')
        werkzeug_logger.disabled = True

        def check_auth(username, password):
            return WEBSERVER_PASSWORD == "" or (username == 'admin' and compare_digest(password, WEBSERVER_PASSWORD))
            
        def login_required(f):
            @wraps(f)
            def wrapped_view(**kwargs):
                auth = request.authorization
                if WEBSERVER_PASSWORD != "" and not (auth and check_auth(auth.username, auth.password)):
                    return ('Unauthorized', 401, {
                        'WWW-Authenticate': 'Basic realm="Login Required"'
                    })

                return f(**kwargs)

            return wrapped_view

        @app.template_filter('tostreamerurl')
        def streamer_url(streamer):
            return streamer.getWebsiteURL()
        

        def humanReadbleSize(num, suffix="B"):
            for unit in ["", "Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi"]:
                if abs(num) < 1024.0:
                    return f"{num:3.1f}{unit}{suffix}"
                num /= 1024.0
            return f"{num:.1f}Yi{suffix}"

        @app.route('/new')
        @login_required
        def mainSite():
            return app.send_static_file('index.html')

        @app.route('/api/basesettings')
        @login_required
        def apiBaseSettings():
            jsonSites = {}
            for site in Bot.loaded_sites:
                jsonSites[site.siteslug] = site.site
            jsonStatus = {}
            for status in Bot.Status:
                jsonStatus[status.value] = Bot.status_messages[status]
            return json.dumps({
                    "sites": jsonSites,
                    "status": jsonStatus,
                })

        @app.route('/api/data')
        @login_required
        def apiData():
            jsonStreamer = []
            for streamer in self.streamers:
                jsonStream = {
                    "site": streamer.siteslug, 
                    "running": streamer.running,
                    "sc": streamer.sc.value,
                    "status": streamer.status(),
                    "url": streamer.getWebsiteURL(),
                    "username": streamer.username
                }
                jsonStreamer.append(jsonStream)
            return json.dumps({
                    "streamers": jsonStreamer,
                    "freeSpace": {
                        "percentage": str(round(OOSDetector.free_space(), 3)),
                        "absolute": humanReadbleSize(OOSDetector.space_usage().free)
                    }
                })

        @app.route('/api/command')
        @login_required
        def execApiCommand():
            return self.execCmd(request.args.get("command"))
    
        @app.route('/')
        @login_required
        def status():
            sites = Bot.loaded_sites
            return render_template('index.html.jinja', streamers=self.streamers, sites=sites, resultStatus="hide", resultMessage="")

        @app.route('/recordings')
        @login_required
        def recordings():
            streamer = self.getStreamer(request.args.get("user"), request.args.get("site"))
            videos = []
            try:
                for elem in os.listdir("./downloads/{u} [{s}]".format(u=streamer.username, s=streamer.siteslug)):
                    videos.append(elem)
            except Exception as e:
                self.logger.warning(e)
            return render_template('recordings.html.jinja', streamer=streamer, videos=sorted(videos, reverse=True))
        
        @app.route('/videos/get/<user>/<site>/<path:filename>')
        def get_video(user, site, filename):
            streamer = self.getStreamer(user, site)
            return send_from_directory(
                "../../downloads/{u} [{s}]".format(u=streamer.username, s=streamer.siteslug),
                filename
            )
        
        @app.route('/videos/watch/<user>/<site>/<path:filename>')
        def watch_video(user, site, filename):
            extension = filename.rsplit('.', 1)[-1]
            return render_template('video.html.jinja', user=user, site=site, filename=filename, extension=extension)

        @app.route('/videos/delete/<user>/<site>/<path:filename>', methods=['DELETE'])
        def delete_video(user, site, filename):
            streamer = None
            videos = []
            videoListError = False
            videoListErrorMessage = None
            try:
                streamer = self.getStreamer(user, site)
                for elem in os.listdir("./downloads/{u} [{s}]".format(u=streamer.username, s=streamer.siteslug)):
                    if(elem == filename):
                        path = os.path.abspath("./downloads/{u} [{s}]/{file}".format(u=streamer.username, s=streamer.siteslug, file=filename))
                        os.remove(path)
                    else:
                        videos.append(elem)
            except Exception as e:
                videoListError = True
                videoListErrorMessage = repr(e)
                self.logger.warning(e)
                
            return render_template('video_list.html.jinja', streamer=streamer, videos=sorted(videos, reverse=True), videoListError=videoListError, videoListErrorMessage=videoListErrorMessage)
        
        @app.route("/add", methods=['POST'])
        def add():
            user = request.form["username"]
            site = request.form["site"]
            resultStatus = "success"
            statusCode = 200
            streamer = self.getStreamer(user, site)
            res = self.do_add(streamer, user, site)
            if(res == 'Streamer already exists' or res == "Missing value(s)" or res == "Failed to add"):
                resultStatus = "error"
                statusCode = 500
            return render_template('streamers_result.html.jinja', streamers=self.streamers, resultStatus=resultStatus, resultMessage=res), statusCode
        
        @app.route("/status/<user>/<site>")
        def get_status(user, site):
            streamer = self.getStreamer(user, site)
            res = None
            statusCode = 200
            if(streamer is None):
                statusCode = 500
                res = "Unknown"
            else:
                res = streamer.status()
            return res,statusCode
        
        @app.route("/remove/<user>/<site>", methods=['DELETE'])
        def remove_streamer(user, site):
            streamer = self.getStreamer(user, site)
            res = self.do_remove(streamer, user, site)
            statusCode = 204
            removeStreamerHasError = False
            if(res == "Failed to remove streamer" or res == "Streamer not found"):
                statusCode = 404
                removeStreamerHasError = True
                return render_template('streamer_record_error.html.jinja', removeStreamerHasError=removeStreamerHasError, removeStreamerResultMessage=res),statusCode
            return '',statusCode
        
        @app.route("/toggle/<user>/<site>", methods=['PATCH'])
        def toggle_streamer(user, site):
            streamer = self.getStreamer(user, site)
            statusCode = 500
            res = "Streamer not found"
            hasError = True
            if(streamer is None):
                statusCode = 500
            elif(streamer.running):
                res = self.do_stop(streamer, user, site)
            else:
                res = self.do_start(streamer, user, site)
            if(res == "OK"):
                hasError = False
                statusCode = 200
            return render_template('streamer_running.html.jinja', streamer=streamer, toggleStreamerResultMessage=res, toggleStreamerHasError=hasError), statusCode
        
        @app.route("/start/all", methods=['PATCH'])
        def start_all_streamers():
            statusCode = 500
            resultStatus = "error"
            try:
                res = self.do_start(None, '*', None)
                if(res == "Started all"):
                    statusCode = 200
                    resultStatus = "success"
            except Exception as e:
                self.logger.warning(e)
                res = str(e)
            return render_template('streamers_result.html.jinja', streamers=self.streamers, resultStatus=resultStatus, resultMessage=res), statusCode
        
        @app.route("/stop/all", methods=['PATCH'])
        def stop_all_streamers():
            statusCode = 500
            resultStatus = "error"
            try:
                res = self.do_stop(None, '*', None)
                if(res == "Stopped all"):
                    statusCode = 200
                    resultStatus = "success"
            except Exception as e:
                self.logger.warning(e)
                res = str(e)
            return render_template('streamers_result.html.jinja', streamers=self.streamers, resultStatus=resultStatus, resultMessage=res), statusCode

        app.run(host=WEBSERVER_HOST, port=WEBSERVER_PORT)
