from flask import Flask, request
import os
from streamonitor.bot import Bot
import streamonitor.log as log
from streamonitor.manager import Manager


class HTTPManager(Manager):
    def __init__(self, streamers):
        super().__init__(streamers)
        self.daemon = True
        self.logger = log.Logger("manager")

    def run(self):
        app = Flask(__name__)

        def header():
            return "<h1>CG-DL Status</h1>"

        def scripts():
            pass

        @app.route('/')
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

        app.run(host='127.0.0.1', port=5000)
