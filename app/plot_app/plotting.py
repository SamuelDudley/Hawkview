""" methods an classes used for plotting (wrappers around bokeh plots) """
from bokeh.plotting import figure

from bokeh.models import (
    ColumnDataSource, Range1d, DataRange1d, DatetimeAxis,
    TickFormatter, DatetimeTickFormatter, FuncTickFormatter,
    Grid, Legend, Plot, BoxAnnotation, Span, CustomJS, Rect, Circle, Line,
    HoverTool, BoxZoomTool, PanTool, WheelZoomTool,
    WMTSTileSource, GMapPlot, GMapOptions,
    LabelSet
    )
from bokeh.models.widgets import DataTable, DateFormatter, TableColumn, Div

from downsampling import DynamicDownsample
import numpy as np
from helper import flight_modes_table

TOOLS = "pan,wheel_zoom,box_zoom,reset,save"
ACTIVE_SCROLL_TOOLS = "wheel_zoom"


def plot_flight_modes_background(p, flight_mode_changes):
    """ plot flight modes as filling background (with different colors) to bokeh
        plot p """
    for ent in flight_mode_changes:
        (mode, t_start, t_end)  = ent
        if mode in flight_modes_table:
            color = flight_modes_table[mode]
            p.add_layout(BoxAnnotation(left=int(t_start), right=int(t_end),
                                       fill_alpha=0.09, line_color=None, fill_color=color))


def plot_set_equal_aspect_ratio(p, x, y, zoom_out_factor=1.3, min_range=5):
    """
    Set plot range and make sure both plotting axis have an equal scaling.
    The plot size must already have been set before calling this.
    """
    x_range = [np.amin(x), np.amax(x)]
    x_diff = x_range[1]-x_range[0]
    if x_diff < min_range: x_diff = min_range
    x_center = (x_range[0]+x_range[1])/2
    y_range = [np.amin(y), np.amax(y)]
    y_diff = y_range[1]-y_range[0]
    if y_diff < min_range: y_diff = min_range
    y_center = (y_range[0]+y_range[1])/2

    # keep same aspect ratio as the plot
    aspect = p.plot_width / p.plot_height
    if aspect > x_diff / y_diff:
        x_diff = y_diff * aspect
    else:
        y_diff = x_diff / aspect

    p.x_range = Range1d(start=x_center - x_diff/2 * zoom_out_factor,
                        end=x_center + x_diff/2 * zoom_out_factor, bounds=None)
    p.y_range = Range1d(start=y_center - y_diff/2 * zoom_out_factor,
                        end=y_center + y_diff/2 * zoom_out_factor, bounds=None)

    p.select_one(BoxZoomTool).match_aspect = True


class DataPlot:
    """
    Handle the bokeh plot generation from an ULog dataset
    """


    def __init__(self, config, x_axis_label=None,
                 y_axis_label=None, title=None, plot_height='normal',
                 y_range=None, y_start=None, changed_params=None, plot_name=None):

        self._had_error = False
        self._previous_success = False
        self._param_change_label = None

        self._config = config
        self._plot_height_name = plot_height
        self.y_min = None
        self.y_max = None
        
        try:
            self._p = figure(title=title, x_axis_label=x_axis_label,
                             y_axis_label=y_axis_label, tools=TOOLS,
                             active_scroll=ACTIVE_SCROLL_TOOLS)
            if y_range is not None:
                self._p.y_range = y_range
            
            if plot_name is not None:
                self._p.name = plot_name
        
        # TODO: support this function
#             if changed_params is not None:
#                 self._param_change_label = \
#                     plot_parameter_changes(self._p, config['plot_height'][plot_height],
#                                            changed_params)

        except (KeyError, IndexError, ValueError) as error:
            print(type(error), ":", error)
            self._had_error = True

    @property
    def bokeh_plot(self):
        """ return the bokeh plot """
        return self._p

    @property
    def param_change_label(self):
        """ returns bokeh LabelSet or None """
        return self._param_change_label


    def add_graph(self, timestamps, field_values, field_names, colors, legends, use_downsample=True):
        """ add 1 or more lines to a graph

        field_names can be a list of fields from the data set, or a list of
        functions with the data set as argument and returning a tuple of
        (field_name, data)
        """
        if self._had_error: return
        try:
            for timestamp, field_value, field_name, color, legend in zip(timestamps, field_values, field_names, colors, legends): 
                p = self._p       
                data_set = {}
                data_set['timestamp'] = timestamp
                data_set[field_name] = field_value
                legend = " "+legend # Legend values will become keywords to data source. Add the space to keep them unique
                if use_downsample:
                    # we directly pass the data_set, downsample and then create the
                    # ColumnDataSource object, which is much faster than
                    # first creating ColumnDataSource, and then downsample
                    downsample = DynamicDownsample(p, data_set, 'timestamp')
                    data_source = downsample.data_source
                else:
                    data_source = ColumnDataSource(data=data_set)
    
                p.line(x='timestamp', y=field_name, source=data_source,
                       legend=legend, line_width=2, line_color=color)

        except (KeyError, IndexError, ValueError) as error:
            print(type(error), "("+self._data_name+"):", error)
            self._had_error = True


    def finalize(self):
        """ Call this after all plots are done. Returns the bokeh plot, or None
        on error """
        if self._had_error and not self._previous_success:
            return None
        self._setup_plot()
        return self._p


    def _setup_plot(self):
        plots_width = self._config['plot_width']
        plots_height = self._config['plot_height'][self._plot_height_name]
        p = self._p

        p.plot_width = plots_width
        p.plot_height = plots_height

        # -> other attributes are set via theme.yaml

        # disable x grid lines
        p.xgrid.grid_line_color = None

        p.ygrid.grid_line_color = 'navy'
        p.ygrid.grid_line_alpha = 0.13
        p.ygrid.minor_grid_line_color = 'navy'
        p.ygrid.minor_grid_line_alpha = 0.05

        #p.lod_threshold=None # turn off level-of-detail

        # axis labels: format time
        p.xaxis[0].formatter = FuncTickFormatter(code='''
                    //func arguments: ticks, x_range
                    // assume us ticks
                    ms = Math.round(tick / 1000)
                    sec = Math.floor(ms / 1000)
                    minutes = Math.floor(sec / 60)
                    hours = Math.floor(minutes / 60)
                    ms = ms % 1000
                    sec = sec % 60
                    minutes = minutes % 60

                    function pad(num, size) {
                        var s = num+"";
                        while (s.length < size) s = "0" + s;
                        return s;
                    }

                    if (hours > 0) {
                        var ret_val = hours + ":" + pad(minutes, 2) + ":" + pad(sec,2)
                    } else {
                        var ret_val = minutes + ":" + pad(sec,2);
                    }
                    if (x_range.end - x_range.start < 4e6) {
                        ret_val = ret_val + "." + pad(ms, 3);
                    }
                    return ret_val;
                ''', args={'x_range' : p.x_range})