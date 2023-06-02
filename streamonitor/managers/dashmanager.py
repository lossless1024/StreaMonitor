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


class DashManager(Manager):
    def __init__(self, streamers):
        super().__init__(streamers)
        self.logger = log.Logger("manager")

    def run(self):
        app = Dash(__name__, title="CG-DL Status", update_title="CG-DL Status",
                   external_stylesheets=["https://raw.githubusercontent.com/necolas/normalize.css/master/normalize.css",
                                         ])

        # remove all css
        app.css.config.serve_locally = False

        # set title
        app.title = "CG-DL Status"

        def header():
            return "<h1>CG-DL Status</h1>"

        def scripts():
            pass

        def status():
            df = pd.DataFrame(
                columns=["Site", "Username", "Started", "Status"])
            for streamer in self.streamers:
                df = df._append({"Site": streamer.site,
                                "Username": streamer.username,
                                 "Started": streamer.running,
                                 "Status": streamer.status()}, ignore_index=True)
            return df

        def recordings():
            streamer = self.getStreamer(
                request.args.get("user"), request.args.get("site"))
            try:
                temp = []
                for elem in os.listdir("./downloads/{u} [{s}]".format(u=streamer.username, s=streamer.siteslug)):
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
                html.H1("CG-DL Status"),
                dcc.Interval(
                    id='interval-component',
                    interval=20*1000,  # in milliseconds
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
                        'backgroundColor': '#303030',
                        'color': colors.white,
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
                                'filter_query': '{Status} = "Unknown error"',
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
                        'backgroundColor': colors.black,
                        'color': colors.white,
                        'font-family': 'font-family: JetBrains Mono, monospace',
                        'fontWeight': 'bold'

                    },
                    sort_mode="multi",
                    sort_action="native",
                    filter_action="native")
            ],
            style={
                'backgroundColor': colors.black,
                'color': colors.white,
                # remove margin for better mobile experience
                'margin': '0px',
                'font-family': 'font-family: JetBrains Mono, monospace'
            })

        @app.callback(
            dependencies.Output('table', 'data'),
            dependencies.Input('interval-component', 'n_intervals'))
        def update_data(timestamp):
            return status().to_dict('records')

        app.run(host="127.0.0.2", port=5000)
