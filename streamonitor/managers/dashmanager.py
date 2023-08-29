from flask import Flask, request
import os
from streamonitor.bot import Bot
import streamonitor.log as log
from streamonitor.manager import Manager
from dash import Dash
from dash import dcc
from dash import html
import plotly.express as px
import pandas as pd
from dash import dash_table
from dash import dependencies
from timeit import default_timer as timer
import time
import shutil
import parameters
import psutil
import json


def load_json(filename: str):
    with open(filename, "r") as f:
        return json.load(f)


def load_settings():
    settings = load_json("web-settings.json")
    return settings


def load_lexicon():
    lex = load_json("web-lexicon.json")
    return lex


UPDATE_INTERVAL = 1  # seconds

# Lexicon for the web interface
lex = load_lexicon()
print(lex)


class DashManager(Manager):
    def __init__(self, streamers):
        super().__init__(streamers)
        self.logger = log.Logger("manager")

    def run(self):
        app = Dash(__name__, title=lex['title'], update_title=None,
                   external_stylesheets=["https://raw.githubusercontent.com/necolas/normalize.css/master/normalize.css",
                                         ])

        app.css.config.serve_locally = False

        app.title = lex['title']

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
            return df

        def recordings():
            streamer = self.getStreamer(
                request.args.get("user"), request.args.get("site"))
            try:
                temp = []
                for elem \
                        in os.listdir("./downloads/{u} [{s}]".
                                      format(u=streamer.username,
                                             s=streamer.siteslug)):
                    temp.append(elem)
                if temp == []:
                    return "No recordings"
                else:
                    return temp
            except:
                return "No recordings"

        class colors:
            green = '#3D9970'
            yellow = '#FFDC00'
            red = '#FF4136'
            grey = '#DDDDDD'
            white = '#EEEEEE'
            black = '#191919'

        app.layout = html.Div(
            [
                html.Div(
                    [
                        html.H1(lex['title']),

                        html.Div(
                            [
                                html.Button(
                                    lex['stop_all'],
                                    id='stop_all',
                                    n_clicks=0
                                ),
                                html.Button(
                                    lex['start_all'],
                                    id='start_all',
                                    n_clicks=0
                                ),
                            ],
                            id="buttons-all-streamers"
                        ),
                        # field to enter username
                        html.Div(children=[
                            dcc.Input(
                                id="username",
                                type="text",
                                placeholder=lex['username'],
                                value="",
                                style={
                                    'max-height': '36px',
                                    'height': '36px',
                                },
                            ),
                            dcc.Dropdown(
                                id="site",
                                options=[
                                    {'label': html.Span(['Chaturbate'], style={
                                                        'background-color': colors.green}),
                                     'value': 'chaturbate'},
                                    {'label': 'OnlyFans', 'value': 'onlyfans'}],
                                className="site-dropdown",
                                placeholder=lex['site'],
                                style={
                                    'width': '100px',
                                    'min-height': '30px',
                                    'height': '40px',
                                    'margin': 0,
                                    'padding': 0,
                                    # 'margin-left': '20px',
                                    'width': '200px',
                                    'border-radius': '10px',
                                    'text-align': 'left',
                                    'font-family': 'font-family: JetBrains Mono, monospace',
                                    'background-color': '#606060',
                                },
                            )
                        ],
                            id="user-manage"
                        ),

                        html.Div(
                            [
                                html.Button(
                                    lex['remove'],
                                    id='remove_streamer',
                                    n_clicks=0
                                ),
                                html.Button(
                                    lex['add'],
                                    id='add_streamer',
                                    n_clicks=0
                                ),
                            ],
                            id="buttons-single-streamer"
                        ),

                        # console output text box
                        html.Div(
                            [
                                html.Pre(
                                    id='console',
                                    children=lex['console_placeholder'],
                                )
                            ],
                            id="console_div"
                        ),

                        html.H3('{} . . .'.format(
                            lex['loading']), id="running"),
                        html.H3('{} . . .'.format(
                            lex['loading']), id="cpu_usage"),
                        html.H3('{} . . .'.format(
                            lex['loading']), id="ram_usage"),
                        html.H3('{} . . .'.format(
                            lex['loading']), id="disk_space"),

                        dcc.Interval(
                            id='interval-component',
                            interval=UPDATE_INTERVAL*1000,  # in milliseconds
                            n_intervals=0
                        ),
                        # sorting fucntionalities
                        dash_table.DataTable(
                            id='table',
                            columns=[{"name": i, "id": i}
                                     for i in status().columns],
                            data=status().to_dict('records'),
                            style_cell={
                                'textAlign': 'left',
                                'backgroundColor': '#2f2f2f',
                                'color': '#EEEEEE',
                                'font-family': 'font-family: JetBrains Mono, monospace'
                            },
                            style_data_conditional=[
                                {
                                    'if': {
                                        'filter_query': '{Status} = "Channel online"',
                                        'column_id': 'Status'
                                    },
                                    'backgroundColor': colors.green,
                                    'color': colors.white,
                                    'font-family': 'font-family: JetBrains Mono, monospace'
                                },
                                {
                                    'if': {
                                        'filter_query': '{Status} = "Private show"',
                                        'column_id': 'Status'
                                    },
                                    'backgroundColor': colors.yellow,
                                    'color': colors.black,
                                    'font-family': 'font-family: JetBrains Mono, monospace'
                                },
                                {
                                    'if': {
                                        'filter_query': '{Status} = "Not running"',
                                        'column_id': 'Status'
                                    },
                                    'backgroundColor': colors.yellow,
                                    'color': colors.black,
                                    'font-family': 'font-family: JetBrains Mono, monospace'
                                },
                                {
                                    'if': {
                                        'filter_query': '{Status} = "Rate limited"',
                                        'column_id': 'Status'
                                    },
                                    'backgroundColor': colors.yellow,
                                    'color': colors.black,
                                    'font-family': 'font-family: JetBrains Mono, monospace'
                                },
                                {
                                    'if': {
                                        'filter_query': '{Status} = "Unknown error"',
                                        'column_id': 'Status'
                                    },
                                    'backgroundColor': colors.red,
                                    'color': colors.white,
                                    'font-family': 'font-family: JetBrains Mono, monospace'
                                },
                                {
                                    'if': {
                                        'filter_query': '{Status} = "Error on downloading"',
                                        'column_id': 'Status'
                                    },
                                    'backgroundColor': colors.red,
                                    'color': colors.white,
                                    'font-family': 'font-family: JetBrains Mono, monospace'
                                },
                                {
                                    'if': {
                                        'filter_query': '{Status} = "No stream for a while"',
                                        'column_id': 'Status'
                                    },
                                    'backgroundColor': colors.grey,
                                    'color': colors.black,
                                    'font-family': 'font-family: JetBrains Mono, monospace'
                                },
                                {
                                    'if': {
                                        'filter_query': '{Status} = "No stream"',
                                        'column_id': 'Status'
                                    },
                                    'backgroundColor': colors.grey,
                                    'color': colors.black,
                                    'font-family': 'font-family: JetBrains Mono, monospace'
                                }
                            ],
                            style_header={
                                'backgroundColor': '#101010',
                                'color': '#EEEEEE',
                                'font-family': 'font-family: JetBrains Mono, monospace',
                                'fontWeight': 'bold'
                            },
                            sort_mode="multi",
                            sort_action="native",
                            filter_action="native"),
                    ],
                    id="main_div"),

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

        # update table

        @app.callback(
            dependencies.Output('table', 'data'),
            dependencies.Input('interval-component', 'n_intervals'))
        def update_data(timestamp):
            return status().to_dict('records')

        # update running
        @app.callback(
            dependencies.Output('running', 'children'),
            dependencies.Input('interval-component', 'n_intervals'))
        def update_running(timestamp):
            return '=> {}: {}/{}'.\
                format(lex['running'],
                       len(status()[status()["Status"] ==
                                    "Channel online"]), len(status()))

        # update cpu usage
        @app.callback(
            dependencies.Output('cpu_usage', 'children'),
            dependencies.Input('interval-component', 'n_intervals'))
        def update_cpu_usage(timestamp):
            return '=> {}: {}%'.format(lex['cpu'], psutil.cpu_percent())

        # update ram usage
        @app.callback(
            dependencies.Output('ram_usage', 'children'),
            dependencies.Input('interval-component', 'n_intervals'))
        def update_ram_usage(timestamp):
            return '=> {}: {}/{} GB'.\
                format(lex['ram'],
                       round(psutil.virtual_memory()[3]/1024/1024/1024, 2),
                       round(psutil.virtual_memory()[0]/1024/1024/1024, 2))

        # update disk space
        @app.callback(
            dependencies.Output('disk_space', 'children'),
            dependencies.Input('interval-component', 'n_intervals'))
        def update_disk_space(timestamp):
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

        app.run(host="127.0.0.1", port=5001)
