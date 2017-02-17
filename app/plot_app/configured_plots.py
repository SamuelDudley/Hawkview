import numpy as np
from bokeh.plotting import figure, curdoc
from bokeh.models import TapTool, CustomJS, ColumnDataSource, LegendItem, Legend
from bokeh.models import LinearAxis, Range1d, BoxAnnotation, HoverTool, Span, Label
import os, json, re, uuid
from colors import get_N_colors

# make a regular expression to extract the words containing capital letters (msg types)
re_caps = re.compile('[A-Z_][A-Z0-9_]+')

from plotting import DataPlot, plot_flight_modes_background
from helper import *
from config import *

def custom_plot_handler(attr, old, new, hawk = None, colors = None, flight_modes = None):
    print("Previous expression: " + old)
    print("Updated expression: " + new)    
    graphs = [{'expression': new, 'handle':'custom_plot'}]
    plots = generate_plots(hawk, graphs, colors, flight_modes)
    
    root_layout = curdoc().get_model_by_name('mainLayout')
    list_of_sub_layouts = root_layout.children
    sub_list_of_sub_layouts = list_of_sub_layouts[0].children
    
    for plot in plots:
        if plot is not None:
            sub_list_of_sub_layouts.append(plot)
    

def generate_plots(hawk, graphs, colors, flight_modes, plots = []):
    """ create a list of bokeh plots (and widgets) to show """

    mestate = hawk.mestate
    
    for graph in graphs:
        gExpression = graph['expression']
        
        try:
            gPath = graph['path']
        except KeyError:
            gPath = ''
        
        try:
            gName = graph['name']
        except KeyError:
            gName = None
            
        try:
            gDescription = graph['description']
        except KeyError:
            gDescription = ''
            
        try:
            gHandle = graph['handle']
        except KeyError:
            gHandle = None
        
        print gExpression, gName, gDescription
        
        msg_types = set() # an empty set
        
        fields = gExpression.split() # extract the fields from the graph expression
        print 'cmd_graph fields input: ',fields
        fields_to_load = set([x.split('.')[0] for x in fields])
        
        for f in fields_to_load:
            caps = set(re.findall(re_caps, f))
            msg_types = msg_types.union(caps)
            
        fields_to_load = list(msg_types) # convert the finished set into a list
        print 'cmd_graph fields to load: ',fields_to_load 
        
        fields_to_load = [x for x in fields_to_load if (x in mestate.mlog.dtypes.keys() and x not in mestate.arrays.keys())]
        if len(fields_to_load) == 0:
            pass
        else:
            hawk.load_np_arrays(fields_to_load)
        
        data_plot = None
        
        colors_index = 0
        
        for field in fields:
            print "plot:", field
            
            if field.endswith(":2"):
                # TODO: add support for more axis
                field = field[:-2]

            y = evaluate_expression(field, mestate.arrays)
            
            if y is None:
                print 'eval failed: ', field
            
            else:
                print y     
                msg_types = set()
                caps = set(re.findall(re_caps, field))
                msg_types = msg_types.union(caps)
                
                x = None
                for msg_type in msg_types:
                    if msg_type in mestate.arrays:
                        x = (mestate.arrays[msg_type]['timestamp']-mestate.mlog.min_timestamp)*1.0e6 # convert to usec from sec
                
                if x is not None:
                    if data_plot is None:
                        data_plot = DataPlot(plot_config, title = gName, plot_name = gHandle)
                        
                    data_plot.add_graph([x], [y], [field], [colors[colors_index]], [field], use_downsample=True)
                    colors_index += 1
                        
        if data_plot is not None:
            plot_flight_modes_background(data_plot.bokeh_plot, flight_modes)
            plot = data_plot.finalize()
            if plot is not None:
                plots.append(plot)
                
    return plots
