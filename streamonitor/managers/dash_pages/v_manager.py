import dash
from dash import Dash
from dash import dcc
from dash import html
from dash import dash_table
from dash import dependencies


dash.register_page(__name__,
                   name='SM - Video Manager',
                   path='/video-manager',
                   order=1)

layout = html.Div([
    html.H1('Video Manager'),
    html.Div('This page is not implemented yet.'),
])
