import dash
from dash import Dash
from dash import dcc
from dash import html
from dash import dash_table

import dash_bootstrap_components as dbc
from streamonitor.managers.dashmanager import lex
from streamonitor.managers.dashmanager import config
from streamonitor.managers.dashmanager import gl_status

dash.register_page(__name__,
                   name='StreaMonitor',
                   path='/',
                   order=0)

layout = html.Div([
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
                    dbc.Button(
                        lex['v_manager'],
                        id='v_manager',
                        href='/video-manager',
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
                        {'label': html.Span(['Amateur.TV'], style={
                            'color': config["color_text_inv"]}),
                            'value': 'ATV'},

                        {'label': html.Span(['BongaCams'], style={
                            'color': config["color_text_inv"]}),
                            'value': 'BC'},

                        {'label': html.Span(['Cam4'], style={
                            'color': config["color_text_inv"]}),
                            'value': 'C4'},

                        {'label': html.Span(['Cams.com'], style={
                            'color': config["color_text_inv"]}),
                            'value': 'CC'},

                        {'label': html.Span(['CamSoda'], style={
                            'color': config["color_text_inv"]}),
                            'value': 'CS'},

                        {'label': html.Span(['Chaturbate'], style={
                            'color': config["color_text_inv"]}),
                            'value': 'CB'},

                        {'label': html.Span(['Cherry.TV'], style={
                            'color': config["color_text_inv"]}),
                            'value': 'CHTV'},

                        {'label': html.Span(['Dreamcam VR'], style={
                            'color': config["color_text_inv"]}),
                            'value': 'DCVR'},

                        {'label': html.Span(['Flirt4Free'], style={
                            'color': config["color_text_inv"]}),
                            'value': 'F4F'},

                        {'label': html.Span(['ManyVids Live'], style={
                            'color': config["color_text_inv"]}),
                            'value': 'MV'},

                        {'label': html.Span(['MyFreeCams'], style={
                            'color': config["color_text_inv"]}),
                            'value': 'MFC'},

                        {'label': html.Span(['SexChat.hu'], style={
                            'color': config["color_text_inv"]}),
                            'value': 'SCHU'},

                        {'label': html.Span(['StreaMate'], style={
                            'color': config["color_text_inv"]}),
                            'value': 'SM'},

                        {'label': html.Span(['StripChat'], style={
                            'color': config["color_text_inv"]}),
                            'value': 'SC'},

                        {'label': html.Span(['StripChat VR'], style={
                            'color': config["color_text_inv"]}),
                            'value': 'SCVR'},
                    ],
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
                        'background-color': config["color_dropdown_background"],
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
                # in milliseconds
                interval=config["update_interval_s"]*1000,
                n_intervals=0
            ),
            # sorting fucntionalities
            dash_table.DataTable(
                id='table',
                columns=[{"name": i, "id": i}
                         for i in gl_status.columns],
                data=gl_status.to_dict('records'),
                style_cell={
                    'textAlign': 'left',
                    'backgroundColor': config["color_cell_background"],
                    'color': config["color_text"],
                    'font-family': 'font-family: JetBrains Mono, monospace'
                },
                style_data_conditional=[
                    {
                        'if': {
                            'filter_query': '{Status} = "Channel online"',
                                            'column_id': 'Status'
                        },
                        'backgroundColor': config["color_positive"],
                        'color': config["color_text"],
                        'font-family': 'font-family: JetBrains Mono, monospace'
                    },
                    {
                        'if': {
                            'filter_query': '{Status} = "Private show"',
                                            'column_id': 'Status'
                        },
                        'backgroundColor': config["color_warning"],
                        'color': config["color_text"],
                        'font-family': 'font-family: JetBrains Mono, monospace'
                    },
                    {
                        'if': {
                            'filter_query': '{Status} = "Not running"',
                                            'column_id': 'Status'
                        },
                        'backgroundColor': config["color_warning"],
                        'color': config["color_text_inv"],
                        'font-family': 'font-family: JetBrains Mono, monospace'
                    },
                    {
                        'if': {
                            'filter_query': '{Status} = "Rate limited"',
                                            'column_id': 'Status'
                        },
                        'backgroundColor': config["color_warning"],
                        'color': config["color_text"],
                        'font-family': 'font-family: JetBrains Mono, monospace'
                    },
                    {
                        'if': {
                            'filter_query': '{Status} = "Unknown error"',
                                            'column_id': 'Status'
                        },
                        'backgroundColor': config["color_negative"],
                        'color': config["color_text"],
                        'font-family': 'font-family: JetBrains Mono, monospace'
                    },
                    {
                        'if': {
                            'filter_query': '{Status} = "Nonexistent user"',
                                            'column_id': 'Status'
                        },
                        'backgroundColor': config["color_negative"],
                        'color': config["color_text"],
                        'font-family': 'font-family: JetBrains Mono, monospace'
                    },
                    {
                        'if': {
                            'filter_query': '{Status} = "Error on downloading"',
                                            'column_id': 'Status'
                        },
                        'backgroundColor': config["color_negative"],
                        'color': config["color_text"],
                        'font-family': 'font-family: JetBrains Mono, monospace'
                    },
                    {
                        'if': {
                            'filter_query': '{Status} = "No stream for a while"',
                                            'column_id': 'Status'
                        },
                        'backgroundColor': config["color_neutral"],
                        'color': config["color_text_inv"],
                        'font-family': 'font-family: JetBrains Mono, monospace'
                    },
                    {
                        'if': {
                            'filter_query': '{Status} = "No stream"',
                                            'column_id': 'Status'
                        },
                        'backgroundColor': config["color_neutral"],
                        'color': config["color_text_inv"],
                        'font-family': 'font-family: JetBrains Mono, monospace'
                    }
                ],
                style_header={
                    'backgroundColor': config["color_table_header_background"],
                    'color': config["color_text"],
                    'font-family': 'font-family: JetBrains Mono, monospace',
                    'fontWeight': 'bold'
                },
                sort_mode="multi",
                sort_action="native",
                filter_action="native"),
        ],
        id="main_div"),
])
