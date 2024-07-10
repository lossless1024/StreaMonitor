import os
import json
import logging

from functools import wraps
from flask import Flask, request
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

        def header():
            return "<h1>CG-DL Status</h1>"

        def scripts():
            pass

        def humanReadbleSize(num, suffix="B"):
            for unit in ["", "Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi"]:
                if abs(num) < 1024.0:
                    return f"{num:3.1f}{unit}{suffix}"
                num /= 1024.0
            return f"{num:.1f}Yi{suffix}"

        @app.route('/')
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
    
        @app.route('/old')
        @login_required
        def status():
            output = header()
            output += """
                <table style="border:1px solid">
                <tr>
                <th>Site</th>
                <th>Username</th>
                <th>Started</th>
                <th>Status</th>
                </tr>"""

            for streamer in self.streamers:
                output += """
                    <tr>
                    <td>{s}</td>
                    <td><a href="/recordings?user={u}&site={s}">{u}</a></td>
                    <td><a onclick="togglerunning({u})">{r}</a></td>
                    <td><a onclick="refreshstatus({u})">{st}</a></td>
                    </tr>""".format(s=streamer.site, r=streamer.running,
                                    st=streamer.status(), u=streamer.username)
            output += "</table>"
            return output

        @app.route('/recordings')
        @login_required
        def recordings():
            output = header()
            streamer = self.getStreamer(request.args.get("user"), request.args.get("site"))
            output += "<p>Recordings of {u} [{s}]</p>".format(u=streamer.username, s=streamer.siteslug)
            try:
                temp = "<p>"
                for elem in os.listdir("./downloads/{u} [{s}]".format(u=streamer.username, s=streamer.siteslug)):
                    temp += elem + "<br>"
                if temp == "<p>":
                    output = "<p>No recordings</p>"
                else:
                    output += temp + "</p>"
            except:
                output += "<p>No recordings</p>"
            return output

        app.run(host=WEBSERVER_HOST, port=WEBSERVER_PORT)
