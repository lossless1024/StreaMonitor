from itertools import islice
import mimetypes
import re
from typing import cast
from flask import Flask, make_response, render_template, request, send_from_directory
import os
import json
import logging
import math

from functools import wraps
from streamonitor.bot import Bot
import streamonitor.log as log
from streamonitor.manager import Manager
from streamonitor.managers.outofspace_detector import OOSDetector
from streamonitor.models import InvalidStreamer
from parameters import WEBSERVER_HOST, WEBSERVER_PORT, WEBSERVER_PASSWORD, WEB_LIST_FREQUENCY, WEB_STATUS_FREQUENCY
from secrets import compare_digest

from streamonitor.utils import get_recording_query_params, get_streamer_context

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

        @app.template_filter('tohumanfilesize')
        def human_file_size(size):
            units = ["B", "KiB", "MiB", "GiB", "TiB", "PiB", "EiB", "ZiB"]
            size = abs(size)
            exponent = math.floor(math.log(size, 1024))
            if(exponent > len(units) - 1):
                return f"{size:.1f}YiB"
            humansize = size / (1024 ** exponent)
            if(humansize >= 1000):
                return f"{humansize:.4g}{units[exponent]}"
            else:
                return f"{humansize:.3g}{units[exponent]}"

        def humanReadbleSize(num, suffix="B"):
            for unit in ["", "Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi"]:
                if abs(num) < 1024.0:
                    return f"{num:3.1f}{unit}{suffix}"
                num /= 1024.0
            return f"{num:.1f}Yi{suffix}"

        @app.route('/simple')
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
    
        @app.route('/', methods=['GET'])
        @login_required
        def status():
            usage = OOSDetector.space_usage()
            context = {
                'streamers': self.streamers,
                'sites': Bot.loaded_sites,
                'free_space': human_file_size(usage.free),
                'total_space': human_file_size(usage.total),
                'percentage_free': round(usage.free / usage.total * 100, 3),
                'refresh_freq': WEB_LIST_FREQUENCY,
            }
            return render_template('index.html.jinja', **context)

        @app.route('/refresh/streamers', methods=['GET'])
        @login_required
        def refresh_streamers():
            context = {
                'streamers': self.streamers,
                'sites': Bot.loaded_sites,
                'refresh_freq': WEB_LIST_FREQUENCY,
                'resultStatus': "hide",
                'resultMessage': "",
            }
            return render_template('streamers_result.html.jinja', **context)

        @app.route('/recordings/<user>/<site>', methods=['GET'])
        @login_required
        def recordings(user, site):
            video = request.args.get("play_video")
            sort_by_size = bool(request.args.get("sorted", False))
            streamer = cast(Bot | None, self.getStreamer(user, site))
            context = get_streamer_context(streamer, sort_by_size, video)
            status_code = 500 if context['videoListError'] else 200
            if (video is None and streamer.recording and len(context['videos']) > 1):
                # It might not always be safe to grab the biggest file if sorting by size, but good enough for now
                video_index = 0 if sort_by_size else 1
                context['video_to_play'] = next(islice(context['videos'].values(), video_index, video_index + 1))
            elif (video is None and len(context['videos']) > 0 and not streamer.recording):
                context['video_to_play'] = next(islice(context['videos'].values(), 0, 1))
            return render_template('recordings.html.jinja', **context), status_code
        
        @app.route('/video/<user>/<site>/<path:filename>', methods=['GET'])
        def get_video(user, site, filename):
            streamer = cast(Bot | None, self.getStreamer(user, site))
            return send_from_directory(
                os.path.abspath(streamer.outputFolder),
                filename
            )
        
        @app.route('/videos/watch/<user>/<site>/<path:play_video>', methods=['GET'])
        @login_required
        def watch_video(user, site, play_video):
            sort_by_size = bool(request.args.get("sorted", False))
            streamer = cast(Bot | None, self.getStreamer(user, site))
            context = get_streamer_context(streamer, sort_by_size, play_video)
            status_code = 500 if context['video_to_play'] is None or context['videoListError'] else 200
            response = make_response(render_template('recordings_content.html.jinja', **context), status_code)
            query_param = get_recording_query_params(sort_by_size, play_video)
            response.headers['HX-Replace-Url'] = f"/recordings/{user}/{site}{query_param}"
            return response
        
        @app.route('/videos/<user>/<site>', methods=['GET'])
        @login_required
        def sort_videos(user, site):
            streamer = cast(Bot | None, self.getStreamer(user, site))
            sort_by_size = bool(request.args.get("sorted", False))
            play_video = request.args.get("play_video", None)
            context = get_streamer_context(streamer, sort_by_size, play_video)
            status_code = 500 if context['videoListError'] else 200
            response = make_response(render_template('video_list.html.jinja', **context), status_code)
            query_param = get_recording_query_params(sort_by_size, play_video)
            response.headers['HX-Replace-Url'] = f"/recordings/{user}/{site}{query_param}"
            return response

        @app.route('/videos/<user>/<site>/<path:filename>', methods=['DELETE'])
        @login_required
        def delete_video(user, site, filename):
            streamer = cast(Bot | None, self.getStreamer(user, site))
            sort_by_size = bool(request.args.get("sorted", False))
            play_video = request.args.get("play_video", None)
            context = get_streamer_context(streamer, sort_by_size, play_video)
            status_code = 200
            match = context['videos'].pop(filename, None)
            if(match is not None):
                try:
                    os.remove(match.abs_path)
                    context['total_size'] = context['total_size'] - match.filesize
                    if(context['video_to_play'] is not None and play_video == context['video_to_play'].filename):
                        context['video_to_play'] = None
                except Exception as e:
                    status_code = 500
                    context['videoListError'] = True
                    context['videoListErrorMessage'] = repr(e)
                    self.logger.error(e)
            else:
                status_code = 404
                context['videoListError'] = True
                context['videoListErrorMessage'] = f'Could not find {filename}, so no file removed'
            response = make_response(render_template('video_list.html.jinja', **context ), status_code)
            query_param = get_recording_query_params(sort_by_size, play_video)
            response.headers['HX-Replace-Url'] = f"/recordings/{user}/{site}{query_param}"
            return response
        
        @app.route("/add", methods=['POST'])
        @login_required
        def add():
            user = request.form["username"]
            site = request.form["site"]
            resultStatus = "success"
            status_code = 200
            streamer = self.getStreamer(user, site)
            res = self.do_add(streamer, user, site)
            if(res == 'Streamer already exists' or res == "Missing value(s)" or res == "Failed to add"):
                resultStatus = "error"
                status_code = 500
            context = {
                'streamers': self.streamers,
                'refresh_freq': WEB_LIST_FREQUENCY,
                'resultStatus': resultStatus,
                'resultMessage': res,
            }
            return render_template('streamers_result.html.jinja', **context), status_code
        
        @app.route("/recording/nav/<user>/<site>")
        @login_required
        def get_streamer_navbar(user, site):
            streamer = self.getStreamer(user, site)
            res = None
            status_code = 200
            has_error = False
            if(streamer is None):
                status_code = 500
                streamer = InvalidStreamer(user, site)
                has_error = True
            context = {
                'streamer': streamer,
                'has_error': has_error,
                'refresh_freq': WEB_STATUS_FREQUENCY,
            }
            return render_template('streamer_nav_bar.html.jinja', **context), status_code
        
        @app.route("/streamer-info/<user>/<site>")
        @login_required
        def get_streamer_info(user, site):
            streamer = self.getStreamer(user, site)
            res = None
            status_code = 200
            has_error = False
            if(streamer is None):
                status_code = 500
                res = f"Could not get info for {user} on site {site}"
                has_error = True
            context = {
                'streamer': streamer,
                'streamerHasError': has_error,
                'streamerErrorMessage': res,
            }
            return render_template('streamer_record.html.jinja', **context), status_code
        
        @app.route("/remove/<user>/<site>", methods=['DELETE'])
        @login_required
        def remove_streamer(user, site):
            streamer = self.getStreamer(user, site)
            res = self.do_remove(streamer, user, site)
            status_code = 204
            removeStreamerHasError = False
            if(res == "Failed to remove streamer" or res == "Streamer not found"):
                status_code = 404
                removeStreamerHasError = True
                context = {
                    'removeStreamerHasError': removeStreamerHasError,
                    'removeStreamerResultMessage': res,
                }
                return render_template('streamer_record_error.html.jinja', **context),status_code
            return '',status_code
        
        @app.route("/toggle/<user>/<site>", methods=['PATCH'])
        @login_required
        def toggle_streamer(user, site):
            streamer = self.getStreamer(user, site)
            status_code = 500
            res = "Streamer not found"
            has_error = True
            if(streamer is None):
                status_code = 500
            elif(streamer.running):
                res = self.do_stop(streamer, user, site)
            else:
                res = self.do_start(streamer, user, site)
            if(res == "OK"):
                has_error = False
                status_code = 200
            context = {
                'streamer': streamer,
                'streamerHasError': has_error,
                'streamerErrorMessage': res,
            }
            return render_template('streamer_record.html.jinja', **context), status_code
        
        @app.route("/start/all", methods=['PATCH'])
        @login_required
        def start_all_streamers():
            status_code = 500
            resultStatus = "error"
            try:
                res = self.do_start(None, '*', None)
                if(res == "Started all"):
                    status_code = 200
                    resultStatus = "success"
            except Exception as e:
                self.logger.warning(e)
                res = str(e)
            context = {
                'streamers': self.streamers,
                'refresh_freq': WEB_LIST_FREQUENCY,
                'resultStatus': resultStatus,
                'resultMessage': res,
            }
            return render_template('streamers_result.html.jinja', **context), status_code
        
        @app.route("/stop/all", methods=['PATCH'])
        @login_required
        def stop_all_streamers():
            status_code = 500
            resultStatus = "error"
            try:
                res = self.do_stop(None, '*', None)
                if(res == "Stopped all"):
                    status_code = 200
                    resultStatus = "success"
            except Exception as e:
                self.logger.warning(e)
                res = str(e)

            context = {
                'streamers': self.streamers,
                'refresh_freq': WEB_LIST_FREQUENCY,
                'resultStatus': resultStatus,
                'resultMessage': res,
            }
            return render_template('streamers_result.html.jinja', **context), status_code

        app.run(host=WEBSERVER_HOST, port=WEBSERVER_PORT, debug=True, use_reloader=False)
