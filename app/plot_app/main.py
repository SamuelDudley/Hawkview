""" module that gets executed on a plotting page request """

from timeit import default_timer as timer
import sys
import sqlite3
import os
import json
from bokeh.io import curdoc
from bokeh.layouts import column, widgetbox
from bokeh.models.widgets import Div
from lib import MAVHawkview

from helper import *
from config import *
from colors import get_N_colors
from configured_plots import generate_plots, custom_plot_handler


start_time = timer()
error_message = ''
log_id = ''


GET_arguments = curdoc().session_context.request.arguments
 
if GET_arguments is not None and 'bokeh-session-id' in GET_arguments:
        log_args = GET_arguments['bokeh-session-id'][0].split(':')[0]
        log_id = log_args

        if not validate_log_id(log_id):
            raise ValueError('Invalid log id: {}'.format(log_id))



        print('GET[log]={}'.format(log_id))

print_timing("Data Loading", start_time)
start_time = timer()


if error_message == '':

    log_path = os.path.join('..','data',log_id) # this points to the folder with the raw np arrays
    # we load hawkview, which will populate the state from the raw np arrays on disk
    hawk = MAVHawkview.Hawkview(log_path, processed_np_save_path = False, raw_np_save_path = False)
    # no np array data is yet loaded into memory...
    hawk.process()
    
    graphs_json = os.path.join(log_path, 'graphs.json')
    
    with open(graphs_json, 'r') as fid:
        graphs = json.load(fid)
        
    colors = get_N_colors(12)
    
    flight_modes = []
    for flight_mode in hawk.mestate.mlog._flightmodes:
        (mode_name, t_start, t_end) = flight_mode
        flight_modes.append((mode_name, (t_start - hawk.mestate.mlog.min_timestamp)*1.0e6, (t_end - hawk.mestate.mlog.min_timestamp)*1.0e6))
    
    plots = []
    
    from bokeh.models.widgets import TextInput
    from functools import partial
    
#     text_input = TextInput(value="", title="Custom Plot Expression")
#     text_input.on_change("value", partial(custom_plot_handler, hawk = hawk, colors = colors, flight_modes = flight_modes))
#     
    plots = generate_plots(hawk, graphs, colors, flight_modes, plots = plots)
    
    title = 'Analysis'

else:

    title = 'Error'

# layout
# layout = column([column([text_input], name='customLayout' )], name='mainLayout')#, sizing_mode='scale_width')
layout = column(plots, name='mainLayout')
curdoc().add_root(layout)
curdoc().title = title

print_timing("Plotting", start_time)