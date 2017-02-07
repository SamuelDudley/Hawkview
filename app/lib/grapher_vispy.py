#!/usr/bin/env python

'''
 core library for graphing in mavexplorer
'''
import numpy as np
import vispy.plot as vp
import matplotlib

from vispy.color import get_colormap

import multiprocessing


import sys, struct, time, os, datetime
import math, re
from math import *

from pymavlink.mavextra import *
from pymavlink import mavutil
from numpy import * #needed for sqrt on arrays


colourmap = {
    'apm' : {
        'MANUAL'    : (1.0,   0,   0),
        'AUTO'      : (  0, 1.0,   0),
        'LOITER'    : (  0,   0, 1.0),
        'FBWA'      : (1.0, 0.5,   0),
        'RTL'       : (  1,   0, 0.5),
        'STABILIZE' : (0.5, 1.0,   0),
        'LAND'      : (  0, 1.0, 0.5),
        'STEERING'  : (0.5,   0, 1.0),
        'HOLD'      : (  0, 0.5, 1.0),
        'ALT_HOLD'  : (1.0, 0.5, 0.5),
        'CIRCLE'    : (0.5, 1.0, 0.5),
        'POSITION'  : (1.0, 0.0, 1.0),
        'GUIDED'    : (0.5, 0.5, 1.0),
        'ACRO'      : (1.0, 1.0,   0),
        'CRUISE'    : (  0, 1.0, 1.0)
        },
    'px4' : {
        'MANUAL'    : (1.0,   0,   0),
        'SEATBELT'  : (  0.5, 0.5,   0),
        'EASY'      : (  0, 1.0,   0),
        'AUTO'    : (  0,   0, 1.0),
        'UNKNOWN'    : (  1.0,   1.0, 1.0)
        }
    }

class Camera_State(object):
    def __init__(self, rect):
        self.rect = rect
        
class Cursor_Location(object):
    # holds the current location of the cursor
    def __init__(self, loc):
        self.loc = loc


class MavGraphVispy(object):
    def __init__(self, recv_queue, send_queue):
        # create figure with plot
        self.fig = vp.Fig(bgcolor='w', size=(800, 600), show=True)
        self.plt = self.fig[0, 0]
        self.plt._configure_2d()
        self.plt.title.text = ''
        self.plt.ylabel.text = ''
        self.plt.xlabel.text = ''
        self.selected = None
        self.fig.connect(self.on_mouse_press)
        self.fig.connect(self.on_mouse_move)
        self.fig.connect(self.on_mouse_wheel)
        self.fig.connect(self.on_key_press)
        self.fig.connect(self.on_draw)
        self.linked = False
        self.fields = []
        self.lables = True
        self.show_grid = False # used to toggle the grid on and off with self.update_grid()
        self.grid = None # holds the grid vispy element
        self.stats = False
        self.xaxis = None
        self.condition = None
        self.flightmodes = []
        self.flightmode_data = []
        self.send_queue = send_queue
        self.recv_queue = recv_queue
        self.cursor_pos_x = None
        self.cursor_pos_y = None
        
    def add_field(self, field):
        '''add another field to plot'''
        self.fields.append(field)
    
    def set_grid(self, choice):
        if choice == 'on':
            choice = True
        elif choice == True:
            pass
        else:
            choice = False
        self.show_grid = choice
        self.update_grid()
    
    def update_grid(self):
        '''control if a grid is shown'''
        if self.show_grid:
            self.grid_on()
        else:
            self.grid_off()
    
    def grid_on(self):
        self.grid = vp.visuals.GridLines(color=(0, 0, 0, 0.5))
        self.grid.set_gl_state('translucent')
        self.grid.order = 9
        self.grid.visible
        self.fig[0, 0].view.add(self.grid)
        
    
    def grid_off(self):
        if self.grid is not None:
            self.grid.visible = False
#             try:
#                 pass #remove grid here
#             except:
#                 print 'error removing grid'
    
    def set_legend(self, choice):
        '''set graph legend'''
        if choice == "upper left":
            self.legend_on()
        else:
            pass
    
    def legend_on(self):
        labelgrid = self.fig[0, 0].view.add_grid(margin=10)
        hspacer = vp.Widget()
        hspacer.stretch = (6, 1)
        labelgrid.add_widget(hspacer, row=0, col=0)
        
        box = vp.Widget(bgcolor=(1, 1, 1, 0.0), border_color=None)
        labelgrid.add_widget(box, row=0, col=1)
        
        vspacer = vp.Widget()
        vspacer.stretch = (1, 2)
        labelgrid.add_widget(vspacer, row=1, col=1)
        
        labels = [vp.Label('%s' % line.label, color=line.true_color, anchor_x='right', anchor_y='center' )
                  for line in self.lines]
#         labels = [vp.Label('%s' % line.label, anchor_x='right', anchor_y='center' )
#                   for line in self.lines]
    
        boxgrid = box.add_grid()
        for i, label in enumerate(labels):
            boxgrid.add_widget(label, row=i, col=0)
        hspacer2 = vp.Widget()
        hspacer2.stretch = (4, 1)
        boxgrid.add_widget(hspacer2, row=0, col=1)

    def set_xaxis(self, xaxis):
        '''set graph xaxis'''
        self.xaxis = xaxis   
        
    def set_condition(self, condition):
        '''set graph condition'''
        self.condition = condition
        
    def set_flightmodes(self, flightmodes):
        '''set graph flightmode(s)'''
        self.flightmodes = flightmodes
    
    def set_flightmode_data(self, flightmode_data):
        '''set graph flightmode'''
        self.flightmode_data = flightmode_data
        
    def set_cam(self, cam_rect):
        self.plt.camera.set_state({'rect':cam_rect})
    
    def get_cam(self):
        return self.plt.camera
        
    def process(self, block=True):
        '''process and display graph'''
        self.msg_types = set()
        self.multiplier = []
        self.field_types = []

        # work out msg types we are interested in
        self.x = []
        self.y = []
        self.modes = []
        self.axes = []
        self.first_only = []
        re_caps = re.compile('[A-Z_][A-Z0-9_]+')
        for f in self.fields:
            caps = set(re.findall(re_caps, f))
            self.msg_types = self.msg_types.union(caps)
            self.field_types.append(caps)

    
    def set_data(self, vars):
        
        self.lines = []
        cmap = get_colormap('hsl', value=0.5)
        colors = cmap.map(np.linspace(0.1, 0.9, len(self.fields)))
        
        msg_types = set()
        field_types = []
        re_caps = re.compile('[A-Z_][A-Z0-9_]+')
        
        for f in self.fields:
            caps = set(re.findall(re_caps, f))
            msg_types = msg_types.union(caps)
        
        x_min = None
        msg_type_min =None
        for msg_type in msg_types:
            if msg_type in vars:
                msg_type_min = evaluate_expression(msg_type+'.min_timestamp', vars)
                msg_type_min
           
            if msg_type_min is not None:
                if x_min is None or msg_type_min < x_min:
                    x_min = msg_type_min


        for i in range(0, len(self.fields)):
            msg_types = set()
            f = self.fields[i]
            if f.endswith(":2"):
                #self.axes[i] = 2
                f = f[:-2]
            if f.endswith(":1"):
                #self.first_only[i] = True
                f = f[:-2]
            caps = set(re.findall(re_caps, f))
            msg_types = msg_types.union(caps)
           
            
            v = evaluate_expression(f, vars)
            
            if self.xaxis is None:
                for msg_type in msg_types:
                    if msg_type in vars:
                        x = evaluate_expression(msg_type+'.timestamp-'+str(x_min), vars)
            else:
                x = mavutil.evaluate_expression(self.xaxis, vars)
            
                    
#             a = np.vectorize(datetime.datetime.fromtimestamp)
# #                     x = range(len(v))
#             print a(evaluate_expression(msg_type+'.timestamp', vars))
            color = colors[i] #set the graph colour from the colour map..
            
            if self.condition:
                #generate masked array in place
                
                mask = evaluate_expression(self.condition, vars) #because the
#                 v = v[mask]
#                 x = x[mask]
                
#                 v.mask = ~v.mask #invet the mask to match the logic of the condition
#                 x = ma.masked_array(x)
#                 
#                 x.mask = v.mask
#                 
#                 v = v.compressed() #makes a copy of the array and uses memory...
#                 x = x.compressed() #perhaps just change the colour of valid parts?
#                 #v = np.extract(evaluate_expression(self.condition, vars), v)

                # false color array
                N = len(x)
                f_color = np.ones((N, 4), dtype=np.float32)
                
                #true color array
                color = np.asarray(color, dtype=np.float32)
                t_color = np.array([color,]*N)
                mask=~mask #invert the mask
                mask = np.repeat(mask, 4)
                mask = mask.reshape((N, 4))
                np.copyto(t_color, f_color, where=mask) #  numpy.copyto(dst, src, casting='same_kind', where=None) # NOTE: in place
                color = t_color
                
                
#             self.reduce_by_flightmodes() #if we have selected a flight mode this will limit what will be shown
            
            
            
            
#             # connection array - does not work with current line, need to plot using base class (not wrapper)
#             connect = np.empty((N-1, 2), np.int32)
#             connect[:, 0] = np.arange(N-1)
#             connect[:, 1] = connect[:, 0] + 1
#             connect[N/2, 1] = N/2  # put a break in the middle
            
            line = self.plt.plot((x, v), color=color)
            line.interactive = True
            line.unfreeze()  # make it so we can add a new property to the instance
            line.data_index = i
            line.x = x
            line.y = v
            line.color = color
            line.true_color = colors[i]
            line.label=f
            line.freeze()
            self.lines.append(line)
            
        self.stats_text_upper = vp.Text("", pos=(0, 0), anchor_x='left', anchor_y='center',
                              font_size=8, parent=self.plt.view.scene)
        
        self.stats_text_lower = vp.Text("", pos=(0, 0), anchor_x='left', anchor_y='center',
                              font_size=8, parent=self.plt.view.scene)
        
        # Build visuals used for cursor
        self.cursor_text = vp.Text("", pos=(0, 0), anchor_x='left', anchor_y='center',
                              font_size=8, parent=self.plt.view.scene)
        self.cursor_line = vp.Line(parent=self.plt.view.scene)
        self.cursor_symbol = vp.Markers(pos=np.array([[0, 0]]), parent=self.plt.view.scene, symbol='+',
                                   face_color='black', edge_color=None, size=8.)
        self.cursor_line.visible = False
        self.cursor_symbol.visible = False
        self.cursor_line.order = 10
        self.cursor_symbol.order = 11
        self.cursor_text.order = 10
        
    def on_draw(self, event):
        master_rect = None
        rect = self.get_cam().get_state()['rect']
        #self.send_queue.put(Camera_State(rect))
        while not self.recv_queue.empty():
            obj = self.recv_queue.get()
            master_rect = obj.rect
        if (self.linked and master_rect != None):
            if master_rect.left != rect.left and master_rect.right != rect.right:
                self.set_cam(obj.rect)
        if self.cursor_line.visible and self.cursor_pos_x is not None:
            self.cursor_line.set_data(np.array([[self.cursor_pos_x, rect.bottom], [self.cursor_pos_x, rect.top]]))
        #self.plt.update()
        
    def on_mouse_press(self, event):
        if not event.handled and event.button == 1:
            if self.selected is not None:
                self.selected.set_data(width=1)
            self.selected = None
            for v in self.fig.visuals_at(event.pos):
                if isinstance(v, vp.LinePlot):
                    self.selected = v
                    break
            if self.selected is not None:
                self.selected.set_data(width=1.5)
            
            self.update_cursor(event.pos)
                
        if not event.handled and event.button == 3:
            self.set_cam(self.cam_home)
            self.update_cursor(event.pos)
            
    
    def on_mouse_wheel(self, event):
        self.update_cursor(event.pos)
    
    def on_mouse_move(self, event):
        self.update_cursor(event.pos)
    
    def update_cursor(self, pos):
        if self.selected is None:
            self.cursor_text.visible = False
            self.cursor_line.visible = False
            self.cursor_symbol.visible = False
        
            self.stats_text_upper.visible = False
            self.stats_text_lower.visible = False
            
        else:
            
            if self.stats:
                cam_rect = self.get_cam().get_state()['rect']

                try:
                    i_left = find_nearest(self.selected.x,cam_rect.left)
                    i_right = find_nearest(self.selected.x,cam_rect.right)
                
                    selected_mean =  np.mean(self.selected.y[i_left:i_right])
                    selected_std = np.std(self.selected.y[i_left:i_right])
                    selected_min =np.min(self.selected.y[i_left:i_right])
                    selected_max = np.max(self.selected.y[i_left:i_right])
                    
                    self.stats_text_upper.text = "mean=%0.2f, std=%0.2f" % (selected_mean,selected_std)
                    self.stats_text_lower.text = "min=%0.2f, max=%0.2f" % (selected_min,selected_max)
                except:
                    pass
            
            # map the mouse position to data coordinates
            tr = self.fig.scene.node_transform(self.selected)
            pos = tr.map(pos)

            # get interpolated y coordinate
            x_cur = pos[0]
            
          
            i = find_nearest(self.selected.x,x_cur)
            
            x = self.selected.x[i]
            y = self.selected.y[i]
            if self.cursor_pos_y != y or self.cursor_pos_x != x:
                self.cursor_pos_x = x
                self.cursor_pos_y = y
                self.send_queue.put(Cursor_Location( (self.cursor_pos_x, self.cursor_pos_y) )) # send the current cursor location to the master process via the IPC
    
                # update cursor
                if self.lables:
                    self.cursor_text.text = "%s: x=%0.2f, y=%0.2f" % (self.selected.label,x, y)
                    
                else:
                    self.cursor_text.text =  "x=%0.2f, y=%0.2f" % (x, y)
                value_offset = np.diff(tr.map([[0, 0], [10, 0]]), axis=0)
          
                self.cursor_text.pos = x + value_offset[0, 0], y + value_offset[0, 1]
                
                stats_offset_upper = np.diff(tr.map([[0, 0], [10, 10]]), axis=0)
                self.stats_text_upper.pos = x + stats_offset_upper[0, 0], y + stats_offset_upper[0, 1]
                
                stats_offset_lower= np.diff(tr.map([[0, 0], [10, 20]]), axis=0)
                self.stats_text_lower.pos = x + stats_offset_lower[0, 0], y + stats_offset_lower[0, 1]
                
                rect = self.plt.view.camera.rect
                self.cursor_symbol.set_data(pos=np.array([[x, y]]))
                self.update_stats()
            if False in [self.cursor_text, self.cursor_line.visible, self.cursor_symbol.visible]:
                self.cursor_text.visible = True
                self.cursor_line.visible = True
                self.cursor_symbol.visible = True
            
    
    def update_stats(self):
            if self.stats:
                self.stats_text_upper.visible = True
                self.stats_text_lower.visible = True
            else:
                # dont show the stats as they are no longer updating...
                self.stats_text_upper.visible = False
                self.stats_text_lower.visible = False
    
    def reduce_by_flightmodes(self, ):
        '''reduce data using flightmode selections'''
        if len(self.flightmodes) == 0:
            return
        all_false = True
        for s in self.flightmodes:
            if s:
                all_false = False
        if all_false:
            # treat all false as all modes wanted'''
            return
        # otherwise there are specific flight modes we have selected to plot
        times = []
        times = [(mode[1],mode[2]) for (idx, mode) in enumerate(self.flightmode_data) if self.flightmodes[idx]]
        
        print 'times', times
        for msg_type in self.mestate.arrays.keys():
            mask = None
            for (t0, t1) in times:
                if mask is not None:
                    mask += (self.mestate.arrays[msg_type].timestamp >= t0) & (self.mestate.arrays[msg_type].timestamp <= t1)
                else:
                    mask = (self.mestate.arrays[msg_type].timestamp >= t0) & (self.mestate.arrays[msg_type].timestamp <= t1)
            
#             mask = ~mask #invert the mask
            print mask
            print len(self.mestate.arrays[msg_type].data)
            self.mestate.arrays[msg_type].data = self.mestate.arrays[msg_type].data[mask]
            print len(self.mestate.arrays[msg_type].data)
            
            
    
    def on_key_press(self, event):
        if event.text == 's':
            self.stats = not self.stats # toggle stats display
            self.update_stats()
            
        elif event.text == 'g':
            self.show_grid = not self.show_grid # toggle grid display
            self.update_grid()
            
        elif event.text == 'm':
            self.show_grid = not self.show_grid # toggle grid display
            self.update_grid()
            
        else:
            print event.text
    
    def show(self):
        self.cam_home = self.get_cam().get_state()['rect']
        self.fig.app.run(allow_interactive=True)
        
        

        
        

def find_nearest(array,value):
    idx = (np.abs(array-value)).argmin()
    return idx

def evaluate_expression(expression, vars): #nicked from mavutil
    '''evaluation an expression'''
    try:
        v =eval(expression, globals(), vars)

    except NameError:
        return None
    except ZeroDivisionError:
        return None
    return v

