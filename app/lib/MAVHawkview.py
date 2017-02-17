#!/usr/bin/env python
'''
log analysis program
hacked from mavexplorer by Andrew Tridgell to open and view (much) larger logs
Samuel Dudley September 2015
'''

import collections

import sys, struct, time, os, datetime, json
import math, re
import Queue
import fnmatch
import threading, multiprocessing
from math import *
from MAVProxy.modules.lib import rline
from MAVProxy.modules.lib import wxconsole
from MAVProxy.modules.lib import grapher

from pymavlink.mavextra import *
from MAVProxy.modules.lib.mp_menu import *
from pymavlink import mavutil
from MAVProxy.modules.lib.mp_settings import MPSettings, MPSetting
from MAVProxy.modules.lib import wxsettings
from lxml import objectify
import pkg_resources
import mavmemlog_np
import numpy as np


class LoadedMlog(object):
    '''mlog object to hold loaded values (no actual file)'''
    def __init__(self):
        self.params = {}
        self.message_field_count = {}
        self.message_count = {}
        self.dtypes = {}
        self.msg_mults = {}
        self.struct_fmts = {}
        self._flightmodes = {}
        self.min_timestamp = None
        self.max_timestamp = None
        
        


class MEStatus(object):
    '''status object to conform with mavproxy structure for modules'''
    def __init__(self):
        self.msgs = {}

class MEState(object):
    '''holds state of MAVExplorer'''
    def __init__(self):
        self.message_count = {}
        self.message_field_count = {}
        self.arrays = dict()
        self.plot_processes = []
        self.send_queues = []
        self.recv_queues = []
        self.master_rect = None
        self.flightmode_list = []
        self.input_queue = Queue.Queue()
        self.rl = None
        #self.console = wxconsole.MessageConsole(title='MAVHawkview')
        self.exit = False
        self.websocket_enabled = None
        
        self.log_max_timestamp = None
        self.log_min_timestamp = None

        
            
        self.status = MEStatus()
        self.settings = MPSettings(
            [ MPSetting('marker', str, '+', 'data marker', tab='Graph'),
              MPSetting('condition', str, None, 'condition'),
              MPSetting('xaxis', str, None, 'xaxis'),
              MPSetting('linestyle', str, None, 'linestyle'),
              MPSetting('flightmode', str, None, 'flightmode', choice=['apm','px4']),
              MPSetting('legend', str, 'upper left', 'legend position'),
              MPSetting('legend2', str, 'upper right', 'legend2 position'),
              MPSetting('grid', str, 'off', 'grid', choice=['on','off'])
              ]
            )

        self.mlog = None
#         self.command_map = command_map
        self.completions = {
            "set"       : ["(SETTING)"],
            "condition" : ["(VARIABLE)"],
            "graph"     : ['(VARIABLE) (VARIABLE) (VARIABLE) (VARIABLE) (VARIABLE) (VARIABLE)'],
            "map"       : ['(VARIABLE) (VARIABLE) (VARIABLE) (VARIABLE) (VARIABLE)']
            }
        self.aliases = {}
        self.graphs = []
        self.flightmode_selections = []
    
    def add_array(self, msg_type, ram=True):
        path_to_np_arr = os.path.join(self.raw_np_save_path, msg_type+'.np')
        
        if ram:
            self.arrays.update({msg_type : MEData(msg_type = msg_type , data = np.fromfile(path_to_np_arr ,dtype = self.mlog.dtypes[msg_type]))})
        else:
            self.arrays.update({msg_type : MEData(msg_type = msg_type , data = np.memmap(path_to_np_arr ,dtype = self.mlog.dtypes[msg_type]))})
            
    
    def get_array(self, msg_type):
        return self.arrays[msg_type].data
    
    def set_data(self, msg_type, data):
        self.arrays[msg_type].data = data
    
    def get_array_names(self):
        return self.arrays.keys()



class graph_tree_state(object):
    def __init__(self, graphs):
        self.prefix = None
        self.graphs = graphs[:]



class GraphDefinition(object):
    '''a pre-defined graph'''
    def __init__(self, name, expression, description):
        self.name = name
        self.expression = expression
        self.description = description


class MEFlightmode(object):
    def __init__(self, number, s_global = None , e_global = None, s_local = None, e_local = None):
        self.number = number
        self.s_global = s_global
        self.e_global = e_global

        self.s_local = s_local
        self.e_local = e_local
        self.duration_local = None
        
    def set_duration_global(self, start, end):
        self.duration_global = e_global - s_global
        
class MEData(collections.MutableMapping):
    """A dictionary that applies an arbitrary key-altering
       function before accessing the keys"""

    def __init__(self, msg_type, data, *args, **kwargs):
        self.name = msg_type
        self.data = data
        self.store = dict()
        self.update(dict(*args, **kwargs))  # use the free update to set keys

    def __getitem__(self, key):
        return self.store[self.__keytransform__(key)]

    def __setitem__(self, key, value):
        self.store[self.__keytransform__(key)] = value

    def __delitem__(self, key):
        del self.store[self.__keytransform__(key)]

    def __iter__(self):
        return iter(self.store)

    def __len__(self):
        return len(self.store)

    def __keytransform__(self, key):
        return key
    
    
# class MEData(object):
#     def __init__(self, type, data):
#         self.type = type
#         self.data = data
#         
#     def get_type(self):
#         return self.type



class Hawkview(object):
    def __init__(self, files, processed_np_save_path = '/tmp/mav/',raw_np_save_path ='/tmp/mav/raw/', debug = False):
        
        self.command_map = {
        'graph'      : (self.cmd_graph,     'display a graph'),
        'set'        : (self.cmd_set,       'control settings'),
        'reload'     : (self.cmd_reload,    'reload graphs'),
        'condition'  : (self.cmd_condition, 'set graph conditions'),
        'param'      : (self.cmd_param,     'show parameters'),
        'save'       : (self.cmd_save,      'save log'),
        'json'       : (self.cmd_json,      'write json files'),
        'load'       : (self.cmd_load,      'laod log'),
        'nparr'      : (self.cmd_write_all_np_arrays, 'save np array'),
        }
        
        self.mestate = MEState()
        self.mestate.debug = debug
        self.debug = debug
        self.mestate.raw_np_save_path = raw_np_save_path
        self.mestate.processed_np_save_path = processed_np_save_path
        self.mestate.rl = rline.rline("MAV> ", self.mestate)
        
        # make a regular expression to extract the words containing capital letters (msg types)
        self.re_caps = re.compile('[A-Z_][A-Z0-9_]+')

        if isinstance(files, list):
            print("Loading %s...\n" % files[0])
            self.mestate.file = files[0]
        elif isinstance(files, basestring):
            print("Loading %s...\n" % files)
            self.mestate.file = files
        else:
            sys.exit(1)
            
        # support for loading pre-processed folders
        if os.path.isdir(files):
            # the file is a folder...
            # try to load the existing info...
            self.is_folder = True
        else:
            self.is_folder = False
        
        
    def process(self, progress_func = False):
        if self.is_folder:
            self.cmd_load(args=[])
        else:
            t0 = time.time()
            mlog = mavutil.mavlink_connection(self.mestate.file, notimestamps=False,
                                              zero_time_base=False)
            if not progress_func:
                progress_func = self.progress_bar
            self.mestate.mlog = mavmemlog_np.mavmemlog(mlog, progress_func, self.mestate.raw_np_save_path)
            self.mestate.status.msgs = mlog.messages
    
            t1 = time.time()
            
            print("\nDone! (%u messages in %.1fs)\n" % (self.mestate.mlog._count, t1-t0))
    
    def cmd_save(self, args):
        import pickle
        mlog_pickle_path = os.path.join(self.mestate.raw_np_save_path, 'mlog.pickle')
        with open(mlog_pickle_path, 'wb') as fid:
            # pickle any of the mlog values needed to re generate the current log from file
            pickle.dump({'params':self.mestate.mlog.params, 'message_field_count':self.mestate.mlog.message_field_count,
                        'message_count':self.mestate.mlog.message_count, 'dtypes':self.mestate.mlog.dtypes,
                        'msg_mults':self.mestate.mlog.msg_mults, 'struct_fmts':self.mestate.mlog.struct_fmts,
                        'flightmodes':self.mestate.mlog._flightmodes, 'log_max_timestamp':self.mestate.mlog.max_timestamp,
                        'log_min_timestamp':self.mestate.mlog.min_timestamp}, fid)
            fid.flush()
        fid.close()
        
        self.load_graphs()
        self.graph_menus(save=True)
        
        self.messages_menu(save=True)
        self.flightmode_menu(save=True)
        self.get_params()
    
    def cmd_load(self, args):
        import pickle
        mlog_pickle_path = os.path.join(self.mestate.file, 'mlog.pickle')
        with open(mlog_pickle_path, 'rb') as fid:
            inst = pickle.load(fid)
        fid.close()
        self.mestate.mlog = LoadedMlog()
        self.mestate.mlog.params = inst['params']
        self.mestate.mlog.message_field_count = inst['message_field_count']
        self.mestate.mlog.message_count = inst['message_count']
        self.mestate.mlog.dtypes = inst['dtypes']
        self.mestate.mlog.msg_mults = inst['msg_mults']
        self.mestate.mlog.struct_fmts = inst['struct_fmts']
        self.mestate.mlog._flightmodes = inst['flightmodes']
        self.mestate.mlog.min_timestamp = inst['log_min_timestamp']
        self.mestate.mlog.max_timestamp = inst['log_max_timestamp']
        self.mestate.raw_np_save_path = self.mestate.file
        
        print("\nDone!")
        
    
    def cmd_write_all_np_arrays(self, args):
        self.load_np_arrays()
        
    
    def cmd_json(self, args):
        import json
        mestate = self.mestate
        
        self.load_np_arrays(['ATT', 'POS'])
        min_timestamp = min(mestate.arrays['POS'].data[:]["timestamp"])#, mestate.arrays['ATT'].min_timestamp)
        max_timestamp = max(mestate.arrays['POS'].data[:]["timestamp"])#, mestate.arrays['ATT'].max_timestamp)
        temp = {'id':"log"}
        data = []
        
        max_length = max(len(mestate.arrays['POS'].data), len(mestate.arrays['ATT'].data))
        min_length = min(len(mestate.arrays['POS'].data), len(mestate.arrays['ATT'].data))
        
        split = (max_timestamp - min_timestamp)/1.0
        print split
         
        
        for msg in mestate.arrays['POS'].data[:]:
            diff = msg["timestamp"] - min_timestamp
            if diff < split:
                data.append([diff, msg["Lng"], msg["Lat"], msg["Alt"]])
            
        entry = {"id":temp['id'],
                 "type":"POS",
                 "data":data}
        with open('POS_json.txt', 'w') as fid:
            fid.write(json.dumps(entry))
            fid.flush()
        fid.close()
        
        print("Done POS!")
        
        data = []
        for msg in mestate.arrays['ATT'].data:
            diff = msg["timestamp"] - min_timestamp
            if msg["timestamp"] < max_timestamp and msg["timestamp"] > min_timestamp:
                data.append([ diff, math.radians(msg["Yaw"]), math.radians(msg["Pitch"]), math.radians(msg["Roll"]) ])
        
        entry = {"id":temp['id'],
                 "type":"ATT",
                 "data":data}
        with open('ATT_json.txt', 'w') as fid:
            fid.write(json.dumps(entry))
            fid.flush()
        fid.close()
            
        print("Done ATT!")
        
        del temp
        del data
        del entry
        
    def cmd_set(self, args):
        '''control MAVExporer options'''
        mestate = self.mestate
        mestate.settings.command(args)

    def cmd_condition(self, args):
        '''control MAVExporer conditions'''
        mestate = self.mestate
        if len(args) == 0:
            print("condition is: %s" % mestate.settings.condition)
            return
        mestate.settings.condition = ' '.join(args)
    
    def cmd_reload(self, args):
        '''reload graphs'''
        mestate = self.mestate
        self.load_graphs()
        self.setup_menus()
        mestate.console.write("Loaded %u graphs\n" % len(mestate.graphs))
    
    def cmd_param(self, args):
        '''show parameters'''
        mestate = self.mestate
        if len(args) > 0:
            wildcard = args[0]
        else:
            wildcard = '*'
        k = sorted(mestate.mlog.params.keys())
        for p in k:
            if fnmatch.fnmatch(str(p).upper(), wildcard.upper()):
                print("%-16.16s %f" % (str(p), mestate.mlog.params[p]))
    
    def get_params(self):
        save_path = self.mestate.raw_np_save_path
        if not os.path.exists(save_path):
            os.makedirs(save_path)
        with open(os.path.join(save_path,'params.json'), 'w') as outfile:
            json.dump(self.mestate.mlog.params, outfile)

    def progress_bar(self, pct, end_val=100, bar_length=100):
        percent = float(pct) / end_val
        hashes = '|' * int(round(percent * bar_length))
        spaces = '-' * (bar_length - len(hashes))
        print("\r[ {0} ] {1}%".format(hashes + spaces, int(round(percent * 100))))
        
    def load_graphs(self):
        '''load graphs from mavgraphs.xml'''
        self.mestate.graphs = []
        gfiles = ['mavgraphs.xml']
        if 'HOME' in os.environ:
            for dirname, dirnames, filenames in os.walk(os.path.join(os.environ['HOME'], ".mavproxy")):
                for filename in filenames:
                    if filename.lower().endswith('.xml'):
                        gfiles.append(os.path.join(dirname, filename))
        for file in gfiles:
            if not os.path.exists(file):
                continue
            if load_graph_xml(open(file).read()):
                print("Loaded %s" % file)
        # also load the built in graphs
        dlist = pkg_resources.resource_listdir("MAVProxy", "tools/graphs")
        for f in dlist:
            raw = pkg_resources.resource_stream("MAVProxy", "tools/graphs/%s" % f).read()
            if self.load_graph_xml(raw):
                print("Loaded %s" % f)
        self.mestate.graphs = sorted(self.mestate.graphs, key=lambda g: g.name)
    
    def have_graph(self, name):
        '''return true if we have a graph of the given name'''
        for g in self.mestate.graphs:
            if g.name == name:
                return True
        return False
    
    def graph_menus(self, save = False):
        '''return menu tree for graphs (recursive)'''
        ret = []
        for i in range(len(self.mestate.graphs)):
            g = self.mestate.graphs[i]
            path = g.name.split('/')
            name = path[-1]
            path = path[:-1]
            ret.append({"name":name, "path":path, "expression":g.expression, "description":g.description })
#             if not save:
#                 ret.add_to_submenu(path, MPMenuItem(name, name, '# graph :%u' % i))
        if save:
            save_path = self.mestate.raw_np_save_path
            import json
            if not os.path.exists(save_path):
                os.makedirs(save_path)
            with open(os.path.join(save_path,'graphs.json'), 'w') as outfile:
                json.dump(ret, outfile)
        return ret

            

    def setup_menus(self):
        '''setup console menus'''
        menu = MPMenuTop([])
        menu.add(MPMenuSubMenu('MAVExplorer',
                               items=[MPMenuItem('Settings', 'Settings', 'menuSettings'),
                                      MPMenuItem('Map', 'Map', '# map')]))
    
        menu.add(self.graph_menus())
        menu.add(MPMenuSubMenu('FlightMode', items=self.flightmode_menu()))
        
        menu.add(MPMenuSubMenu('Messages', items=self.messages_menu()))
    
        self.mestate.console.set_menu(menu, self.menu_callback)
        
    def menu_callback(self, m):
        '''called on menu selection'''
        if m.returnkey.startswith('# '):
            cmd = m.returnkey[2:]
            if m.handler is not None:
                if m.handler_result is None:
                    return
                cmd += m.handler_result
            self.process_stdin(cmd)
        elif m.returnkey == 'menuSettings':
            wxsettings.WXSettings(self.mestate.settings)
        elif m.returnkey.startswith("mode-"):
            idx = int(m.returnkey[5:])
            self.mestate.flightmode_selections[idx] = m.IsChecked()
        else:
            print('Unknown menu selection: %s' % m.returnkey)
    
    def load_graph_xml(self, xml):
        '''load a graph from one xml string'''
        try:
            root = objectify.fromstring(xml)
        except Exception:
            return False
        if root.tag != 'graphs':
            return False
        if not hasattr(root, 'graph'):
            return False
        for g in root.graph:
            name = g.attrib['name']
            if self.have_graph(name):
                continue
            expressions = [e.text for e in g.expression]
            for e in expressions:
                graph_ok = True
                fields = e.split()
                for f in fields:
                    try:
                        if f.endswith(':2'):
                            f = f[:-2]
                        if mavutil.evaluate_expression(f, self.mestate.status.msgs) is None:
                            graph_ok = False                        
                    except Exception:
                        graph_ok = False
                        break
                if graph_ok:
                    self.mestate.graphs.append(GraphDefinition(name, e, g.description.text))
                    break
        return True
    
    def flightmode_menu(self, save = False):
        '''construct flightmode menu'''
        modes = self.mestate.mlog.flightmode_list()
        ret = []
        for (mode,t1,t2) in modes:
            print t1, t2
            modestr = "%s %us" % (mode, (t2-t1))
            ret.append({"name":mode, "start":t1, "end":t2})
        
        if save:
            save_path = self.mestate.raw_np_save_path
            import json
            if not os.path.exists(save_path):
                os.makedirs(save_path)
            with open(os.path.join(save_path,'flightmodes.json'), 'w') as outfile:
                json.dump(ret, outfile)
        
        return ret
    
    def messages_menu(self, save=False):
        '''construct messages menu'''
        msgs = self.mestate.mlog.message_field_count.keys()
        ret = []
        for msg in msgs:
            ret.append({"name":msg, "count":self.mestate.mlog.message_count[msg],"fields":self.mestate.mlog.message_field_count[msg]})
#             msgstr = "%s" % (str(self.mestate.mlog.message_count[msg])+' : '+msg+' '+str(self.mestate.mlog.message_field_count[msg]))
#             ret.append(msgstr)
#         print ret
        if save:
            save_path = self.mestate.raw_np_save_path
            
            import json
            if not os.path.exists(save_path):
                os.makedirs(save_path)
            with open(os.path.join(save_path,'messages.json'), 'w') as outfile:
                json.dump(ret, outfile)
        return ret
    
    def main_loop(self):
        '''main processing loop, display graphs and maps'''
        while True:
            if self.mestate is None or self.mestate.exit:
                return
            while not self.mestate.input_queue.empty():
                line = self.mestate.input_queue.get()
                cmds = line.split(';')
                for c in cmds:
                    self.process_stdin(c)
            
            
            for idx,queue in enumerate(self.mestate.recv_queues):
                if idx == 0:
                    obj = None
                    while not queue.empty():
                        obj = queue.get()
                    
                    if obj is not None:
                        if isinstance(obj, Camera_State):
                            self.mestate.master_rect = obj.rect
                            
                        elif isinstance(obj, Cursor_Location): # handle cursor location from the graph
                            try:   
                               (x,y)= obj.loc
                               import eventlet
                               from flask_socketio import SocketIO
                               import redis
                               eventlet.monkey_patch()
                               socketio = SocketIO(message_queue='redis://')
                               socketio.emit('log_time_control', {'log_time': x}, namespace='/test')
                            except:
                               pass
                        else:
                            print obj
                            pass
                            
    
                
                else:
                    slave_rect = None
                    while not queue.empty():
                        obj = queue.get()
#                         slave_rect = obj.rect
                        
#                     if slave_rect is not None and self.mestate.master_rect is not None:
#                         slave_rect.left = self.mestate.master_rect.left
#                         slave_rect.right = self.mestate.master_rect.right
#                         self.mestate.send_queues[idx].put(Camera_Control(slave_rect))
                        
            time.sleep(0.1)
            
            
            

    
    def process_stdin(self, line):
        '''handle commands from user'''
        if line is None:
            sys.exit(0)
    
        line = line.strip()
        if not line:
            return
    
        args = line.split()
        cmd = args[0]
        if cmd == 'help':
            k = self.command_map.keys()
            k.sort()
            for cmd in k:
                (fn, help) = self.command_map[cmd]
                print("%-15s : %s" % (cmd, help))
            return
        if cmd == 'exit':
            self.mestate.exit = True
            return
    
        if not cmd in self.command_map:
            print("Unknown command '%s'" % line)
            return
        (fn, help) = self.command_map[cmd]
        try:
            fn(args[1:])
        except Exception as e:
            print("ERROR in command %s: %s" % (args[1:], str(e)))
    
    def load_np_arrays(self, msg_types=None, ram=True):
        print 'existing', self.mestate.get_array_names()
        if msg_types is not None:
            msg_types = [x for x in msg_types if ((x in self.mestate.mlog.dtypes.keys()) and (x not in self.mestate.arrays.keys()))]
            
        else:
            msg_types = [x for x in self.mestate.mlog.dtypes.keys() if x not in self.mestate.arrays.keys()]
        print 'loading', msg_types
        for msg_type in msg_types:
            
            self.mestate.add_array(msg_type, ram=ram)
            # we have loaded the array, but we cant do operations on it simply as the datatypes are set.
            
            fmt_list = []
            # step over the array datatype structure
            for x in range(len(self.mestate.mlog.dtypes[msg_type])):
                t = self.mestate.mlog.dtypes[msg_type][x]
                if np.issubdtype(t, str): # if the datatype is a string then keep it
                    fmt_list.append(t)
                else:
                    fmt_list.append(np.dtype('float64')) # attempt to convert all the non-strings / numbers to doubles

            double_type = np.dtype(zip(self.mestate.mlog.message_field_count[msg_type],fmt_list))
            # re cast the array for use
            try:
                self.mestate.set_data(msg_type, self.mestate.get_array(msg_type).astype(dtype=double_type, casting='safe', subok=False, copy=False))
                continue_processing = True
            except TypeError as e:
                print ('Error type casting array. Skipping', msg_type, e)
                continue_processing = False
            
            if continue_processing:
                #we have built the float64 array.... now apply the atts.
                
                for col_name in self.mestate.mlog.message_field_count[msg_type]:
                    setattr(self.mestate.arrays[msg_type], col_name, self.mestate.get_array(msg_type)[:][col_name])
                    self.mestate.arrays[msg_type][col_name] = getattr(self.mestate.arrays[msg_type], col_name)
                    col_multi = self.mestate.mlog.msg_mults[msg_type][col_name]
        #             print col_name, col_multi
                    if col_multi is not None:
                        self.mestate.get_array(msg_type)[:][col_name]*= float(col_multi)
                        
                #save the new numpy array
                
                if self.mestate.processed_np_save_path:
                    save_path = self.mestate.processed_np_save_path
                
                    a = self.mestate.get_array(msg_type).astype(dtype=double_type, casting='safe', subok=False, copy=False)
                    if not os.path.exists(save_path):
                        os.makedirs(save_path)
                    np.save(os.path.join(save_path,msg_type), a)

                        
                msg_type_min_timestamp = np.min(self.mestate.arrays[msg_type].timestamp)
                msg_type_max_timestamp = np.max(self.mestate.arrays[msg_type].timestamp)
                  
                setattr(self.mestate.arrays[msg_type], 'min_timestamp', msg_type_min_timestamp)
                setattr(self.mestate.arrays[msg_type], 'max_timestamp', msg_type_max_timestamp)
                
                if self.mestate.mlog.min_timestamp is None:
                    self.mestate.mlog.min_timestamp = msg_type_min_timestamp
                    
                elif self.mestate.mlog.min_timestamp > msg_type_min_timestamp:
                    self.mestate.mlog.min_timestamp = msg_type_min_timestamp
                
                else:
                    pass
                
                if self.mestate.mlog.max_timestamp is None:
                    self.mestate.mlog.max_timestamp = msg_type_max_timestamp
                    
                elif self.mestate.mlog.max_timestamp < msg_type_max_timestamp:
                    self.mestate.mlog.max_timestamp = msg_type_max_timestamp
                    
                else:
                    pass
                
                
                # report the final size of the array to the console
                print msg_type, (self.mestate.arrays[msg_type].data.nbytes)*10**-6, 'MiB'
    
    def cmd_graph(self, args):
        '''graph command'''
        mestate = self.mestate
        usage = "usage: graph <FIELD...>"
        if len(args) < 1:
            print(usage)
            return
        if args[0][0] == ':':
            i = int(args[0][1:])
            g = mestate.graphs[i]
            expression = g.expression
            args = expression.split()
            print("Added graph: %s\n" % g.name)
            if g.description:
                print("%s\n" % g.description)
        print("Expression: %s\n" % ' '.join(args))
        
        send_queue = multiprocessing.Queue()
        recv_queue = multiprocessing.Queue() 
        args.append(send_queue)
        args.append(recv_queue)
        
        
        msg_types = set() # an empty set
        
        fields = args[0:-2] # extract the fields from the args sent to this fn
        if self.debug:
            print 'cmd_graph fields input: ',fields
        fields_to_load = set([x.split('.')[0] for x in fields])
        
        for f in fields_to_load:
            caps = set(re.findall(self.re_caps, f))
            msg_types = msg_types.union(caps)
        fields_to_load = list(msg_types) # convert the finished set into a list
        if self.debug:
            print 'cmd_graph fields to load: ',fields_to_load 
        #check to see if we have already loaded the fields...
        fields_to_load = [x for x in fields_to_load if (x in mestate.mlog.dtypes.keys() and x not in mestate.arrays.keys())]
        if len(fields_to_load) == 0:
            pass
        else:
            self.load_np_arrays(msg_types=fields_to_load)
        
        mestate.send_queues.append(send_queue)
        mestate.recv_queues.append(recv_queue)
        
if __name__ == "__main__":
    from argparse import ArgumentParser
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("files", metavar="<FILE>", nargs="+")
    args = parser.parse_args()

    if len(args.files) == 0:
        print("Usage: MAVHawkview FILE")
        sys.exit(1)
        
    hawk = Hawkview(args.files, debug=True)
    # run main loop as a thread
    hawk.mestate.thread = threading.Thread(target=hawk.main_loop, name='main_loop')
    hawk.mestate.thread.daemon = True
    hawk.mestate.thread.start()
    hawk.process()
#     hawk.load_graphs()
#     hawk.setup_menus()
    
    # input loop
    while True:
        try:
            try:
                line = raw_input(hawk.mestate.rl.prompt)
            except EOFError:
                hawk.mestate.exit = True
                break
            hawk.mestate.input_queue.put(line)
        except KeyboardInterrupt:
            hawk.mestate.exit = True
            break
