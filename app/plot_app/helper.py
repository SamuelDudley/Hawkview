from timeit import default_timer as timer
import time
import re
import os

import numpy as np

from config import debug_print_timing

def validate_log_id(log_id):
    """ Check whether the log_id has a valid form (not whether it actually
    exists) """
    # we are a bit less restrictive than the actual format
    if re.match(r'^[0-9a-zA-Z_-]+$', log_id):
        return True
    return False

def print_timing(name, start_time):
    """ for debugging: print elapsed time, with start_time = timer(). """
    if debug_print_timing():
        print(name + " took: {:.3} s".format(timer() - start_time))
        
def evaluate_expression(expression, vars): #from mavutil
    '''evaluation an expression'''
    try:
        v =eval(expression, globals(), vars)

    except NameError:
        return None
    except ZeroDivisionError:
        return None
    return v

# TODO: add more ardupilot flight modes
flight_modes_table = {
    'MANUAL': '#cc0000', # red
    'UNKNOWN': '#222222', # gray
    'AUTO': '#00cc33', # green
#     6: ('Acro', '#66cc00'), # olive
#     8: ('Stabilized', '#0033cc'), # dark blue
#     7: ('Offboard', '#00cccc'), # light blue
#     9: ('Rattitude', '#cc9900'), # orange
# 
#     3: ('Mission', '#6600cc'), # purple
#     4: ('Loiter', '#6600cc'), # purple
#     5: ('Return to Land', '#6600cc'), # purple
#     10: ('Takeoff', '#6600cc'), # purple
#     11: ('Land', '#6600cc'), # purple
#     12: ('Follow Target', '#6600cc'), # purple
    }