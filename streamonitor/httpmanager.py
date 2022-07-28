from threading import Thread
from flask import Flask, request
import os
from streamonitor.bot import Bot


class HTTPManager(Thread):
    def __init__(self, streamers):
        super().__init__()
        self.streamers = streamers

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
                    <td>{}</td>
                    <td><a href="/recordings?user={u}">{u}</a></td>
                    <td><a onclick="togglerunning({u})">{}</a></td>
                    <td><a onclick="refreshstatus({u})">{}</a></td>
                    </tr>""".format(self.streamers[streamer].site, self.streamers[streamer].running,
                                    self.streamers[streamer].status(), u=self.streamers[streamer].username)
            output += "</table>"
            return output

        @app.route('/recordings')
        def recordings():
            output = header()
            user = self.streamers[request.args["user"]]
            output += "<p>Recordings of {u}</p>".format(u=user.username)
            try:
                temp = "<p>"
                for elem in os.listdir("./downloads/{u} [{s}]".format(u=user.username, s=user.siteslug)):
                    temp += elem + "<br>"
                if temp == "<p>":
                    output = "<p>No recordings</p>"
                else:
                    output += temp + "</p>"
            except:
                output += "<p>No recordings</p>"
            return output

        app.run(host='127.0.0.1', port=5000)
