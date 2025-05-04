from itertools import islice
import mimetypes
import re
from typing import List, cast
from flask import Flask, make_response, render_template, request, send_from_directory
import os
import json
import logging
import math

from functools import wraps
from streamonitor.bot import Bot
from streamonitor.enums import Status
import streamonitor.log as log
from streamonitor.manager import Manager
from streamonitor.managers.outofspace_detector import OOSDetector
from streamonitor.models import InvalidStreamer
from parameters import WEBSERVER_HOST, WEBSERVER_PORT, WEBSERVER_PASSWORD, WEB_LIST_FREQUENCY, WEB_STATUS_FREQUENCY
from secrets import compare_digest

from streamonitor.utils import streamer_list, get_recording_query_params, get_streamer_context, human_file_size
from streamonitor.mappers import web_status_lookup

class HTTPManager(Manager):
    def __init__(self, streamers):
        super().__init__(streamers)
        self.logger = log.Logger("manager")
    
    def run(self):
        app = Flask(__name__, "", "../../web")
        werkzeug_logger = logging.getLogger('werkzeug')
        werkzeug_logger.disabled = True

        app.add_template_filter(human_file_size, name='tohumanfilesize')

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
            for status in Status:
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
                'unique_sites': set(map(lambda x: x.site, self.streamers)),
                'streamer_statuses': web_status_lookup,
                'free_space': human_file_size(usage.free),
                'total_space': human_file_size(usage.total),
                'percentage_free': round(usage.free / usage.total * 100, 3),
                'refresh_freq': WEB_LIST_FREQUENCY,
            }
            return render_template('index.html.jinja', **context)

        @app.route('/refresh/streamers', methods=['GET'])
        @login_required
        def refresh_streamers():
            username_filter = request.args.get("filter-username", None)
            site_filter = request.args.get("filter-site", None)
            status_filter = request.args.get("filter-status", None)
            streamers = streamer_list(self.streamers, username_filter, site_filter, status_filter)
            context = {
                'streamers': streamers,
                'sites': Bot.loaded_sites,
                'refresh_freq': WEB_LIST_FREQUENCY,
                'toast_status': "hide",
                'toast_message': "",
            }
            return render_template('streamers_result.html.jinja', **context)

        @app.route('/recordings/<user>/<site>', methods=['GET'])
        @login_required
        def recordings(user, site):
            video = request.args.get("play_video")
            sort_by_size = bool(request.args.get("sorted", False))
            streamer = cast(Bot | None, self.getStreamer(user, site))
            context = get_streamer_context(streamer, sort_by_size, video)
            status_code = 500 if context['has_error'] else 200
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
            status_code = 500 if context['video_to_play'] is None or context['has_error'] else 200
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
            status_code = 500 if context['has_error'] else 200
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
                    if(context['video_to_play'] is not None and filename == context['video_to_play'].filename):
                        context['video_to_play'] = None
                except Exception as e:
                    status_code = 500
                    context['has_error'] = True
                    context['recordings_error_message'] = repr(e)
                    self.logger.error(e)
            else:
                status_code = 404
                context['has_error'] = True
                context['recordings_error_message'] = f'Could not find {filename}, so no file removed'
            response = make_response(render_template('video_list.html.jinja', **context ), status_code)
            query_param = get_recording_query_params(sort_by_size, play_video)
            response.headers['HX-Replace-Url'] = f"/recordings/{user}/{site}{query_param}"
            return response
        
        @app.route("/add", methods=['POST'])
        @login_required
        def add():
            user = request.form["username"]
            site = request.form["site"]
            username_filter = request.form.get("filter-username", None)
            site_filter = request.form.get("filter-site", None)
            status_filter = request.form.get("filter-status", None)
            update_site_options = site not in map(lambda x: x.site, self.streamers)
            streamers = streamer_list(self.streamers, username_filter, site_filter, status_filter)
            toast_status = "success"
            status_code = 200
            streamer = self.getStreamer(user, site)
            res = self.do_add(streamer, user, site)
            if(res == 'Streamer already exists' or res == "Missing value(s)" or res == "Failed to add"):
                toast_status = "error"
                status_code = 500
            context = {
                'streamers': streamers,
                'unique_sites': set(map(lambda x: x.site, self.streamers)),
                'update_filter_site_options': update_site_options,
                'site_filter': site_filter,
                'refresh_freq': WEB_LIST_FREQUENCY,
                'toast_status': toast_status,
                'toast_message': res,
            }
            return render_template('streamers_result.html.jinja', **context), status_code
        
        @app.route("/recording/nav/<user>/<site>", methods=['GET'])
        @login_required
        def get_streamer_navbar(user, site):
            streamer = self.getStreamer(user, site)
            sort_by_size = bool(request.args.get("sorted", False))
            play_video = request.args.get("play_video", None)
            previous_state = request.args.get("prev_state", False)
            streamer_context = {}
            #need this from the UI perspective to know whether to update due to polling windows
            if(previous_state != streamer.status_icon):
                streamer_context = get_streamer_context(streamer, sort_by_size, play_video)
            status_code = 200
            has_error = False
            if(streamer is None):
                status_code = 500
                streamer = InvalidStreamer(user, site)
                has_error = True
            context = {
                **streamer_context,
                'update_content': False if len(streamer_context) == 0 else True,
                'streamer': streamer,
                'has_error': has_error,
                'refresh_freq': WEB_STATUS_FREQUENCY,
            }
            return render_template('streamer_nav_bar.html.jinja', **context), status_code
        
        @app.route("/streamer-info/<user>/<site>", methods=['GET'])
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
                'streamer_has_error': has_error,
                'streamer_error_message': res,
            }
            return render_template('streamer_record.html.jinja', **context), status_code
        
        @app.route("/remove/<user>/<site>", methods=['DELETE'])
        @login_required
        def remove_streamer(user, site):
            streamer = self.getStreamer(user, site)
            res = self.do_remove(streamer, user, site)
            status_code = 204
            if(res == "Failed to remove streamer" or res == "Streamer not found"):
                status_code = 404
                context = {
                    'streamer_error_message': res,
                }
                response = make_response(render_template('streamer_record_error.html.jinja', **context),status_code)
                response.headers['HX-Retarget'] = "#error-container"
                return response
            return '',status_code
        
        @app.route("/clear", methods=['DELETE'])
        def clear_modal():
            return '',204
        
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
                'streamer_has_error': has_error,
                'streamer_error_message': res,
            }
            return render_template('streamer_record.html.jinja', **context), status_code
        
        @app.route("/toggle/<user>/<site>/recording", methods=['PATCH'])
        @login_required
        def toggle_streamer_recording_page(user, site):
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
                'streamer_has_error': has_error,
                'streamer_error_message': res,
            }
            return render_template('streamer_toggle.html.jinja', **context), status_code
        
        @app.route("/start/streamers", methods=['PATCH'])
        @login_required
        def start_streamers():
            status_code = 500
            toast_status = "error"
            username_filter = request.args.get("filter-username", None)
            site_filter = request.args.get("filter-site", None)
            status_filter = request.args.get("filter-status", None)
            streamers = streamer_list(self.streamers, username_filter, site_filter, status_filter)
            res = ""
            error_message = ""
            try:
                if(len(streamers) == len(self.streamers)):
                    res = self.do_start(None, '*', None)
                    if(res == "Started all"):
                        status_code = 200
                        toast_status = "success"
                else:
                    error = []
                    for streamer in streamers:
                        partial_res = self.do_start(streamer, None, None)
                        if(partial_res != "OK"):
                            error.append(streamer.username)
                    else:
                        res = 'no matching streamers'
                    if(len(error) > 0):
                        toast_status = "warning"
                        res = "Some Failed to Start"
                        error_message = f"The following streamers failed to start:\n {'\n'.join(error)}"
                    else:
                        status_code = 200
                        toast_status = "success"
            except Exception as e:
                self.logger.warning(e)
                res = str(e)
            context = {
                'streamers': streamers,
                'refresh_freq': WEB_LIST_FREQUENCY,
                'toast_status': toast_status,
                'toast_message': res,
                'error_message': error_message,
            }
            return render_template('streamers_result.html.jinja', **context), status_code
        
        @app.route("/stop/streamers", methods=['PATCH'])
        @login_required
        def stop_streamers():
            status_code = 500
            toast_status = "error"
            username_filter = request.args.get("filter-username", None)
            site_filter = request.args.get("filter-site", None)
            status_filter = request.args.get("filter-status", None)
            streamers = streamer_list(self.streamers, username_filter, site_filter, status_filter)
            res = ""
            error_message = ""
            try:
                if(len(streamers) == len(self.streamers)):
                    res = self.do_stop(None, '*', None)
                    if(res == "Stopped all"):
                        status_code = 200
                        toast_status = "success"
                else:
                    error = []
                    for streamer in streamers:
                        partial_res = self.do_stop(streamer, None, None)
                        if(partial_res != "OK"):
                            error.append(streamer.username)
                    else:
                        res = 'no matching streamers'
                    if(len(error) > 0):
                        toast_status = "warning"
                        res = "Some Failed to Stop"
                        error_message = f"The following streamers failed to start:\n {'\n'.join(error)}"
                    else:
                        status_code = 200
                        toast_status = "success"
            except Exception as e:
                self.logger.warning(e)
                res = str(e)

            context = {
                'streamers': streamers,
                'refresh_freq': WEB_LIST_FREQUENCY,
                'toast_status': toast_status,
                'toast_message': res,
                'error_message': error_message,
            }
            return render_template('streamers_result.html.jinja', **context), status_code

        app.run(host=WEBSERVER_HOST, port=WEBSERVER_PORT)
