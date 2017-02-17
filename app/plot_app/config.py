""" configuration variables """

import configparser
import os
from colors import get_N_colors

# load the config
_conf = configparser.ConfigParser()
_cur_dir = os.path.dirname(os.path.realpath(__file__))
_conf.read_file(open(os.path.join(_cur_dir, '../config_default.ini')))

__PRINT_TIMING = int(_conf.get('debug', 'print_timing'))

# general configuration variables for plotting
plot_width = 900

plot_color_blue = '#2877a2' # or: #3539e0

plot_config = dict(
    maps_line_color = plot_color_blue,
    plot_width = plot_width,
    plot_height = dict(
        normal = int(plot_width / 2.1),
        small = int(plot_width / 2.5),
        ),
    )

colors3 = ['#e0212d', '#208900', plot_color_blue]
colors2 = [colors3[0], colors3[1]] # for data to express: 'what it is' and 'what it should be'
colors8 = get_N_colors(8, 0.7)
color_gray = '#464646'

plot_config['mission_setpoint_color'] = colors8[4]

def debug_print_timing():
    """ print timing information? """
    return __PRINT_TIMING == 1
