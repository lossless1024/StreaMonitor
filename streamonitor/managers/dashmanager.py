from flask import Flask, request
import os
from streamonitor.bot import Bot
import streamonitor.log as log
from streamonitor.manager import Manager
import pandas as pd
import datetime

import dash
from dash import Dash, dcc, callback, html, dash_table, dependencies
# from dash import Input
# from dash import Output
# from dash import State

from dash_extensions.enrich import DashProxy, Input, Output, \
    html, MultiplexerTransform, State

from timeit import default_timer as timer
import time
import shutil
import parameters
import psutil

from streamonitor.managers.jsonmanager import JsonWorker


# load lexicon
lex = JsonWorker.load("./config/web-lexicon.json")
# load config
config = JsonWorker.load("./config/web-config.json")
# null df
gl_status = pd.DataFrame(
    columns=[lex['site'], lex['username'],
             lex['started'], lex['status']])


app = DashProxy(__name__,
                prevent_initial_callbacks=True,
                transforms=[MultiplexerTransform()],
                title=lex['title'], update_title=None,
                external_stylesheets=["https://raw.githubusercontent.com/necolas/normalize.css/master/normalize.css",
                                      ],
                use_pages=True, pages_folder="dash_pages")

app.css.config.serve_locally = False


class DashManager(Manager):
    def __init__(self, streamers):
        super().__init__(streamers)
        self.logger = log.Logger("manager")

    def run(self):
        def scripts():
            pass

        def status():
            df = pd.DataFrame(
                columns=[lex['site'], lex['username'],
                         lex['started'], lex['status']])
            for streamer in self.streamers:
                df = df._append({lex['site']: streamer.site,
                                lex['username']: streamer.username,
                                 lex['started']: streamer.running,
                                 lex['status']: streamer.status()},
                                ignore_index=True)

            gl_status = df
            return df

        status()

        app.layout = html.Div(
            [
                dash.page_container,
                html.Div(
                    [
                        html.Div(
                            html.A(lex['credits']),
                            id="credits",
                        ),
                        html.Div(
                            html.A(lex['versions']),
                            id="versions",
                        ),
                    ],
                    id="credit-version-box",
                ),
            ]
        )

        @app.callback(
            dependencies.Output('table', 'data'),
            dependencies.Input('interval-component', 'n_intervals'))
        def update_data(timestamp):
            # update table
            # status()
            return status().to_dict('records')

        @app.callback(
            dependencies.Output('running', 'children'),
            dependencies.Input('interval-component', 'n_intervals'))
        def update_running(timestamp):
            # update running
            return '=> {}: {}/{}'.\
                format(lex['running'],
                       len(status()[status()["Status"] ==
                                    "Channel online"]), len(status()))

        @app.callback(
            dependencies.Output('cpu_usage', 'children'),
            dependencies.Input('interval-component', 'n_intervals'))
        def update_cpu_usage(timestamp):
            # update cpu usage
            return '=> {}: {}%'.format(lex['cpu'], psutil.cpu_percent())

        @app.callback(
            dependencies.Output('ram_usage', 'children'),
            dependencies.Input('interval-component', 'n_intervals'))
        def update_ram_usage(timestamp):
            # update ram usage
            return '=> {}: {}/{} GB'.\
                format(lex['ram'],
                       round(psutil.virtual_memory()[3]/1024/1024/1024, 2),
                       round(psutil.virtual_memory()[0]/1024/1024/1024, 2))

        @app.callback(
            dependencies.Output('disk_space', 'children'),
            dependencies.Input('interval-component', 'n_intervals'))
        def update_disk_space(timestamp):
            # update disk space
            return '=> {}: {}/{} {} ({} = {} {})'.\
                format(lex['harddrive'],
                       round(shutil.disk_usage("./")[1]/1024/1024/1024, 2),
                       round(shutil.disk_usage("./")[0]/1024/1024/1024, 2),
                       lex['gigabyte'],
                       lex['limit'],
                       round(shutil.disk_usage("./")[0]/1024 *
                             (100-parameters.MIN_FREE_DISK_PERCENT) /
                             1024/1024/100, 2),
                       lex['gigabyte'])

        @app.callback(
            Output('console', 'children'),
            Input('stop_all', 'n_clicks'))
        def update_stop_all():
            reply = self.execCmd('stop *')
            return datetime.datetime.now().__str__() + ' >> ' + reply

        @app.callback(
            Output('console', 'children'),
            Input('start_all', 'n_clicks'))
        def update_start_all():
            reply = self.execCmd('start *')
            return datetime.datetime.now().__str__() + ' >> ' + reply

        @app.callback(
            Output('console', 'children'),
            Input('remove_streamer', 'n_clicks'),
            State('username', 'value'))
        def update_remove_streamer(n_clicks, username):
            reply = self.execCmd('remove ' + username)
            return datetime.datetime.now().__str__() + ' >> ' + reply

        @app.callback(
            Output('console', 'children'),
            Input('add_streamer', 'n_clicks'),
            State('username', 'value'),
            State('site', 'value'))
        def update_add_streamer(n_clicks, username, site):
            reply = self.execCmd('add ' + username + ' ' + site)
            return datetime.datetime.now().__str__() + ' >> ' + reply

            # dose_of_sex

        app.run(host="127.0.0.1", port=5001)
