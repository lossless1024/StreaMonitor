from itertools import islice
from typing import cast, Union

from flask import Flask, make_response, render_template, request, send_from_directory, Response
import os
import json
import logging

from parameters import WEBSERVER_HOST, WEBSERVER_PORT, WEBSERVER_PASSWORD, WEB_LIST_FREQUENCY, WEB_STATUS_FREQUENCY, \
    WEBSERVER_SKIN
import streamonitor.log as log
from functools import wraps
from secrets import compare_digest
from streamonitor.bot import Bot, LOADED_SITES
from streamonitor.enums import Status
from streamonitor.manager import Manager
from streamonitor.managers.outofspace_detector import OOSDetector
from streamonitor.utils import human_file_size

from .filters import status_icon, status_text
from .mappers import web_status_lookup
from .models import InvalidStreamer
from .utils import confirm_deletes, streamer_list, get_recording_query_params, get_streamer_context, set_streamer_list_cookies


class HTTPManager(Manager):
    def __init__(self, streamers):
        super().__init__(streamers)
        self.logger = log.Logger("manager")
        self.loaded_site_names = [site.site for site in LOADED_SITES]
        self.loaded_site_names.sort()

        skin = WEBSERVER_SKIN
        if skin in os.listdir(os.path.join(os.path.dirname(__file__), 'skins')):
            self.skin = skin
        else:
            raise ValueError(f'Invalid skin name: {skin}')

    def run(self):
        app = Flask(
            __name__,
            template_folder=f'skins/{self.skin}/templates'
        )
        
        werkzeug_logger = logging.getLogger('werkzeug')
        werkzeug_logger.disabled = True

        app.add_template_filter(human_file_size, name='tohumanfilesize')
        app.add_template_filter(status_icon, name='status_icon_class')
        app.add_template_filter(status_text, name='status_text')

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

        @app.route('/dashboard')
        @login_required
        def mainSite():
            return app.send_static_file('index.html')

        @app.route('/api/basesettings')
        @login_required
        def apiBaseSettings():
            json_sites = {}
            for site in LOADED_SITES:
                json_sites[site.siteslug] = site.site
            json_status = {}
            for status in Status:
                json_status[status.value] = Bot.status_messages[status]
            return Response(json.dumps({
                "sites": json_sites,
                "status": json_status,
            }), mimetype='application/json')

        @app.route('/api/data')
        @login_required
        def apiData():
            json_streamer = []
            for streamer in self.streamers:
                json_stream = {
                    "site": streamer.siteslug,
                    "running": streamer.running,
                    "recording": streamer.recording,
                    "sc": streamer.sc.value,
                    "status": streamer.status(),
                    "url": streamer.url,
                    "username": streamer.username
                }
                json_streamer.append(json_stream)
            return Response(json.dumps({
                "streamers": json_streamer,
                "freeSpace": {
                    "percentage": str(round(OOSDetector.free_space(), 3)),
                    "absolute": human_file_size(OOSDetector.space_usage().free)
                }
            }), mimetype='application/json')

        @app.route('/api/command')
        @login_required
        def execApiCommand():
            return self.execCmd(request.args.get("command"))

        @app.route('/', methods=['GET'])
        @login_required
        def status():
            usage = OOSDetector.space_usage()
            streamers, filter_context = streamer_list(self.streamers, request)
            context = {
                'streamers': streamers,
                'sites': self.loaded_site_names,
                'unique_sites': set(map(lambda x: x.site, self.streamers)),
                'streamer_statuses': web_status_lookup,
                'free_space': human_file_size(usage.free),
                'total_space': human_file_size(usage.total),
                'percentage_free': round(usage.free / usage.total * 100, 3),
                'refresh_freq': WEB_LIST_FREQUENCY,
                'confirm_deletes': confirm_deletes(request.headers.get('User-Agent')),
            } | filter_context
            return render_template('index.html.jinja', **context)

        @app.route('/refresh/streamers', methods=['GET'])
        @login_required
        def refresh_streamers():
            streamers, filter_context = streamer_list(self.streamers, request)
            context = {
                'streamers': streamers,
                'sites': LOADED_SITES,
                'refresh_freq': WEB_LIST_FREQUENCY,
                'toast_status': "hide",
                'toast_message': "",
                'confirm_deletes': confirm_deletes(request.headers.get('User-Agent')),
            } | filter_context
            response = make_response(render_template('streamers_result.html.jinja', **context))
            set_streamer_list_cookies(filter_context, request, response)
            return response

        @app.route('/recordings/<user>/<site>', methods=['GET'])
        @login_required
        def recordings(user, site):
            video = request.args.get("play_video")
            sort_by_size = bool(request.args.get("sorted", False))
            streamer = cast(Union[Bot, None], self.getStreamer(user, site))
            streamer.cache_file_list()
            context = get_streamer_context(streamer, sort_by_size, video, request.headers.get('User-Agent'))
            status_code = 500 if context['has_error'] else 200
            if video is None and streamer.recording and len(context['videos']) > 1:
                # It might not always be safe to grab the biggest file if sorting by size, but good enough for now
                video_index = 0 if sort_by_size else 1
                context['video_to_play'] = next(islice(context['videos'].values(), video_index, video_index + 1))
            elif video is None and len(context['videos']) > 0 and not streamer.recording:
                context['video_to_play'] = next(islice(context['videos'].values(), 0, 1))
            return render_template('recordings.html.jinja', **context), status_code

        @app.route('/video/<user>/<site>/<path:filename>', methods=['GET'])
        def get_video(user, site, filename):
            streamer = cast(Union[Bot, None], self.getStreamer(user, site))
            return send_from_directory(
                os.path.abspath(streamer.outputFolder),
                filename
            )

        @app.route('/videos/watch/<user>/<site>/<path:play_video>', methods=['GET'])
        @login_required
        def watch_video(user, site, play_video):
            sort_by_size = bool(request.args.get("sorted", False))
            streamer = cast(Union[Bot, None], self.getStreamer(user, site))
            context = get_streamer_context(streamer, sort_by_size, play_video, request.headers.get('User-Agent'))
            status_code = 500 if context['video_to_play'] is None or context['has_error'] else 200
            response = make_response(render_template('recordings_content.html.jinja', **context), status_code)
            query_param = get_recording_query_params(sort_by_size, play_video)
            response.headers['HX-Replace-Url'] = f"/recordings/{user}/{site}{query_param}"
            return response

        @app.route('/videos/<user>/<site>', methods=['GET'])
        @login_required
        def sort_videos(user, site):
            streamer = cast(Union[Bot, None], self.getStreamer(user, site))
            sort_by_size = bool(request.args.get("sorted", False))
            play_video = request.args.get("play_video", None)
            context = get_streamer_context(streamer, sort_by_size, play_video, request.headers.get('User-Agent'))
            status_code = 500 if context['has_error'] else 200
            response = make_response(render_template('video_list.html.jinja', **context), status_code)
            query_param = get_recording_query_params(sort_by_size, play_video)
            response.headers['HX-Replace-Url'] = f"/recordings/{user}/{site}{query_param}"
            return response

        @app.route('/videos/<user>/<site>/<path:filename>', methods=['DELETE'])
        @login_required
        def delete_video(user, site, filename):
            streamer = cast(Union[Bot, None], self.getStreamer(user, site))
            sort_by_size = bool(request.args.get("sorted", False))
            play_video = request.args.get("play_video", None)
            context = get_streamer_context(streamer, sort_by_size, play_video, request.headers.get('User-Agent'))
            status_code = 200
            match = context['videos'].pop(filename, None)
            if match is not None:
                try:
                    os.remove(match.abs_path)
                    streamer.cache_file_list()
                    context['total_size'] = context['total_size'] - match.filesize
                    if context['video_to_play'] is not None and filename == context['video_to_play'].filename:
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
            response = make_response(render_template('video_list.html.jinja', **context), status_code)
            query_param = get_recording_query_params(sort_by_size, play_video)
            response.headers['HX-Replace-Url'] = f"/recordings/{user}/{site}{query_param}"
            return response

        @app.route("/add", methods=['POST'])
        @login_required
        def add():
            user = request.form["username"]
            site = request.form["site"]
            update_site_options = site not in map(lambda x: x.site, self.streamers)
            toast_status = "success"
            status_code = 200
            streamer = self.getStreamer(user, site)
            res = self.do_add(streamer, user, site)
            streamers, filter_context = streamer_list(self.streamers, request)
            if res == 'Streamer already exists' or res == "Missing value(s)" or res == "Failed to add":
                toast_status = "error"
                status_code = 500
            context = {
                'streamers': streamers,
                'unique_sites': set(map(lambda x: x.site, self.streamers)),
                'update_filter_site_options': update_site_options,
                'refresh_freq': WEB_LIST_FREQUENCY,
                'toast_status': toast_status,
                'toast_message': res,
                'confirm_deletes': confirm_deletes(request.headers.get('User-Agent')),
            } | filter_context
            return render_template('streamers_result.html.jinja', **context), status_code

        @app.route("/recording/nav/<user>/<site>", methods=['GET'])
        @login_required
        def get_streamer_navbar(user, site):
            streamer = self.getStreamer(user, site)
            sort_by_size = bool(request.args.get("sorted", False))
            play_video = request.args.get("play_video", None)
            previous_state = request.args.get("prev_state", False)
            streamer_context = {}
            # need this from the UI perspective to know whether to update due to polling windows
            if previous_state != streamer.sc:
                streamer_context = get_streamer_context(
                    streamer, sort_by_size, play_video, request.headers.get('User-Agent'))
            status_code = 200
            has_error = False
            if streamer is None:
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
            if streamer is None:
                status_code = 500
                res = f"Could not get info for {user} on site {site}"
                has_error = True
            streamer.cache_file_list()
            context = {
                'streamer': streamer,
                'streamer_has_error': has_error,
                'streamer_error_message': res,
                'confirm_deletes': confirm_deletes(request.headers.get('User-Agent')),
            }
            return render_template('streamer_record.html.jinja', **context), status_code

        @app.route("/remove/<user>/<site>", methods=['DELETE'])
        @login_required
        def remove_streamer(user, site):
            streamer = self.getStreamer(user, site)
            res = self.do_remove(streamer, user, site)
            status_code = 204
            if res == "Failed to remove streamer" or res == "Streamer not found":
                status_code = 404
                context = {
                    'streamer_error_message': res,
                }
                response = make_response(render_template('streamer_record_error.html.jinja', **context), status_code)
                response.headers['HX-Retarget'] = "#error-container"
                return response
            return '', status_code

        @app.route("/clear", methods=['DELETE'])
        def clear_modal():
            return '', 204

        @app.route("/toggle/<user>/<site>", methods=['PATCH'])
        @login_required
        def toggle_streamer(user, site):
            streamer = self.getStreamer(user, site)
            status_code = 500
            res = "Streamer not found"
            has_error = True
            if streamer is None:
                status_code = 500
            elif streamer.running:
                res = self.do_stop(streamer, user, site)
            else:
                res = self.do_start(streamer, user, site)
            if res == "OK":
                has_error = False
                status_code = 200
            context = {
                'streamer': streamer,
                'streamer_has_error': has_error,
                'streamer_error_message': res,
                'confirm_deletes': confirm_deletes(request.headers.get('User-Agent')),
            }
            return render_template('streamer_record.html.jinja', **context), status_code

        @app.route("/toggle/<user>/<site>/recording", methods=['PATCH'])
        @login_required
        def toggle_streamer_recording_page(user, site):
            streamer = self.getStreamer(user, site)
            status_code = 500
            res = "Streamer not found"
            has_error = True
            if streamer is None:
                status_code = 500
            elif streamer.running:
                res = self.do_stop(streamer, user, site)
            else:
                res = self.do_start(streamer, user, site)
            if res == "OK":
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
            streamers, filter_context = streamer_list(self.streamers, request)
            res = ""
            error_message = ""
            try:
                if not filter_context.get('filtered') or len(streamers) == len(self.streamers):
                    res = self.do_start(None, '*', None)
                    if res == "Started all":
                        status_code = 200
                        toast_status = "success"
                else:
                    error = []
                    if len(streamers) > 0:
                        for streamer in streamers:
                            partial_res = self.do_start(streamer, None, None)
                            if partial_res != "OK":
                                error.append(streamer.username)
                        res = "Started All Shown"
                    else:
                        res = 'no matching streamers'
                    if len(error) > 0:
                        toast_status = "warning"
                        res = "Some Failed to Start"
                        error_message = "The following streamers failed to start:\n " + '\n'.join(error)
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
                'confirm_deletes': confirm_deletes(request.headers.get('User-Agent')),
            } | filter_context
            return render_template('streamers_result.html.jinja', **context), status_code

        @app.route("/stop/streamers", methods=['PATCH'])
        @login_required
        def stop_streamers():
            status_code = 500
            toast_status = "error"
            streamers, filter_context = streamer_list(self.streamers, request)
            res = ""
            error_message = ""
            try:
                if not filter_context.get('filtered') or len(streamers) == len(self.streamers):
                    res = self.do_stop(None, '*', None)
                    if res == "Stopped all":
                        status_code = 200
                        toast_status = "success"
                else:
                    error = []
                    if len(streamers) > 0:
                        for streamer in streamers:
                            partial_res = self.do_stop(streamer, None, None)
                            if partial_res != "OK":
                                error.append(streamer.username)
                        res = "Stopped All Shown"
                    else:
                        res = 'no matching streamers'
                    if len(error) > 0:
                        toast_status = "warning"
                        res = "Some Failed to Stop"
                        error_message = "The following streamers failed to stop:\n" + '\n'.join(error)
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
                'confirm_deletes': confirm_deletes(request.headers.get('User-Agent')),
            } | filter_context
            return render_template('streamers_result.html.jinja', **context), status_code

        app.run(host=WEBSERVER_HOST, port=WEBSERVER_PORT)
