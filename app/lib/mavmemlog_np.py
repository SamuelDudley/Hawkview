'''
Mavlink log to numpy array writer
Hacked from mavmemlog by Andrew Tridgell to process large logs and save them as numpy arrays
Samuel Dudley  2015

Note: While binary logs are self describing, tlogs require the correct pymavlink dialects to
be available otherwise the messages will be ignored as [BAD_DATA]
'''

import os, shutil, sys, struct
from pymavlink import mavutil
import numpy as np

class mavmemlog(mavutil.mavfile):
    '''a MAVLink log in memory. The aim of this class is to generate discreet files so we don't
    have to keep sweeping the entire log each time we want to obtain / process data'''
    def __init__(self, mav, progress_callback=None, write_dir = '/tmp/mav'):
        mavutil.mavfile.__init__(self, None, 'memlog')
        self._msgs = []
        self._count = 0
        self.rewind()
        self._flightmodes = []
        last_flightmode = None
        last_timestamp = None
        last_pct = 0
        
        self.ignore = ['BAD_DATA']
        self.write_flag = False
        self.fds = {}
        self.dtypes = {}
        self.msg_mults = {}
        self.struct_fmts= {}
        
        self.message_count = {}
        self.message_field_count = {}
        
        
        self.mav_file_reader = mav.__class__.__name__
        
        if self.mav_file_reader == 'mavlogfile':
            self.is_binary_flash_log = False
        elif self.mav_file_reader == 'DFReader_binary':
            self.is_binary_flash_log = True
        else:
            print ('Error loading filetype:', self.mav_file_reader)
            sys.exit()
        
        if not os.path.exists(write_dir):
            os.makedirs(write_dir)
        
        for the_file in os.listdir(write_dir):
            file_path = os.path.join(write_dir, the_file)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path): shutil.rmtree(file_path)
            except Exception, e:
                print e
                
        
        while True:
            m = mav.recv_msg()
            if m is None:
                break
            
            if int(mav.percent) != last_pct and progress_callback:
                progress_callback(int(mav.percent))
                last_pct = int(mav.percent)
            
            
            msg_type = m.get_type()
            if msg_type in self.ignore:
                self.write_flag = False
            else:
                self.write_flag = True

            
            if msg_type not in self.message_count.keys() and self.write_flag:
                # if this is the first of the msg type
                self.message_count[msg_type] = 0
                if self.is_binary_flash_log:
                    struct_fmt = m.fmt.msg_struct # a string used to describe how to pack the vars of a BIN file
                else:
                    struct_fmt = m.format # a string used to describe how to pack the vars of a tlog file
                struct_fmt+='d' # add a double to hold the common timestamp
                self.struct_fmts[msg_type] = struct_fmt
                
                if self.is_binary_flash_log:
                    struct_columns = m.fmt.columns # the names of the cols of a BIN
                else:
                    struct_columns = m.ordered_fieldnames # the names of the cols of a tlog
                struct_columns.append('timestamp') # add a common timestamp col
                
                if self.is_binary_flash_log:
                    msg_mults = m.fmt.msg_mults # mults to apply later (for BIN)
                else:
                    msg_mults = [None]*len(m.ordered_fieldnames) # mults don't apply to tlogs
                    
                msg_mults.append(None) #for the timestamp
                self.msg_mults[msg_type]= {key:value for key, value in zip(struct_columns,msg_mults)}
                
                self.fds[msg_type] = open(os.path.join(write_dir, msg_type+'.np'), 'ab') # open a binary file to write the msg fields
                struct_fmt_list = []
                digit_string = ''
                for char in struct_fmt: # read the structure format one chr at a time
                    
                    if char == 's': # if its a string
                        char = 'S' # replace lower case s with upper case s to make numpy happy
                        
                    if char.isdigit(): # if its a digit then keep track of it
                        digit_string+=char
                    else:
                        if len(digit_string) != 0: # if we have any stored digits
                            struct_fmt_list.append(digit_string+char) # reverse the order so np.dtype() can work out the correct size
                            digit_string = ''
                        else:
                            struct_fmt_list.append(char) # we have no stored digits
                            
                struct_fmt = struct_fmt_list
                
                
                # print ([struct_fmt[0]+x for x in struct_fmt[1:]])
                try:
                    struct_formats = [struct_fmt[0]+x for x in struct_fmt[1:]]
                    msg_dtype = np.dtype(zip(struct_columns,struct_formats)) # make the struct datatype for this msg
                except TypeError as e:
                    print ('Failed to build numpy data for message type:', msg_type, struct_columns, struct_formats, e)
                    self.write_flag = False
                self.dtypes[msg_type] = msg_dtype # store the dtype against its msg type
                # get the field names and make columns
                self.message_field_count[msg_type] = struct_columns
                        
            if self.write_flag:
                self.message_count[msg_type] += 1
                if self.is_binary_flash_log:
                    struct_elements = m._elements # the raw values of a BIN
                else:
                    struct_elements = [m.to_dict()[x] for x in m.ordered_fieldnames if x != 'timestamp']
                
                struct_elements.append(m._timestamp)
                
                embedded_list_flag = True
                
                while embedded_list_flag:
                    for idx, element in enumerate(struct_elements):
                        if isinstance(element, list): # there is an embedded list within the msg structure
                            embedded_list_flag = True
                            struct_elements[idx:idx+1] = element # insert  the list back into the struct_elements in place [a, b, [c, d, e], f, g] --> [a, b, c, d, e, f, g]                                          
                            break # we have modified the msg structure, break the for loop and start the iteration over the elements again
                        else:
                            embedded_list_flag = False
                            
                self.fds[msg_type].write(struct.pack(self.struct_fmts[msg_type], *struct_elements)) # write the data as a new row in the numpy array

            if mav.flightmode != last_flightmode:
                if len(self._flightmodes) > 0:
                    (mode, t1, t2) = self._flightmodes[-1]
                    self._flightmodes[-1] = (mode, t1, m._timestamp)
                self._flightmodes.append((mav.flightmode, m._timestamp, None))
                last_flightmode = mav.flightmode
            self._count += 1
            last_timestamp = m._timestamp
            self.check_param(m)
        if last_timestamp is not None and len(self._flightmodes) > 0:
            (mode, t1, t2) = self._flightmodes[-1]
            self._flightmodes[-1] = (mode, t1, last_timestamp)
            
        self.close_fds() # close all numpy arrays
        
        if progress_callback:
            progress_callback(int(100))
        mav.data = None # release the memory, no longer needed :)
        
    def close_fds(self):
        for key in self.fds.keys():
            self.fds[key].flush()
            self.fds[key].close()
        
    def check_param(self, m):
        msg_type = m.get_type()
        if msg_type == 'PARAM_VALUE':
            s = str(m.param_id)
            self.params[str(m.param_id)] = m.param_value
        elif msg_type == 'PARM' and getattr(m, 'Name', None) is not None:
            self.params[m.Name] = m.Value

    def flightmode_list(self):
        '''return list of all flightmodes as tuple of mode and start time'''
        return self._flightmodes