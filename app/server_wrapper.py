import tornado
import tornado.ioloop
import tornado.options
import tornado.autoreload
import sys

from bokeh.server.server import Server
from bokeh.command.util import build_single_handler_applications
from plot_app.config import __FLASK_PORT as FLASK_PORT

import os
import psutil
import subprocess

import threading
import time

import signal
import time

class bokeh_server_wrapper(object):
    def __init__(self, bok_io_loop = tornado.ioloop.IOLoop.instance(), port = 5009):
        self.memory_usage = 0
        self.active_connections = 0
        self.port = port
        self.bok_io_loop = bok_io_loop
        self.ser = None
        self.sessions = None
        self.exit = False
        self.new_session_timeout = 20
        self.session_timeout = 1
        self.session_info = {}
        
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)
    
    def exit_gracefully(self, signum, frame):
        self.exit = True
        self.stop_server()
        
    def setup_bokeh_server(self):
        ##turn file paths into bokeh apps
        files = ['plot_app']
        argvs = {}
        for i in files:
            argvs[i]=None
        apps = build_single_handler_applications(files,argvs)
        ##args lifted from bokeh serve call to Server, with the addition of my own io_loop
        kwags = {
            'io_loop':self.bok_io_loop,
            'generade_session_ids':True,
            'redirect_root':True,
            'use_x_headers':False,
            'check_unused_sessions_milliseconds':1000,
            'unused_session_lifetime_milliseconds':5000,
            'secret_key':None,
            'num_procs':1,
            'host':['%s:%d'%('127.0.0.1',FLASK_PORT),'%s:%d'%('127.0.0.1',self.port)],
            'sign_sessions':False,
            'develop':False,
            'port':self.port,
            'use_index':True
        }
        self.ser = Server(apps,**kwags)
    
    def get_sessions(self):
        self.sessions = self.ser.get_sessions('/plot_app') #Gets all live sessions for an application
        print self.sessions
        if len(self.sessions) == 0:
            print('No sessions')
            if not 'global' in self.session_info:
                self.session_info['global'] = {'timeout':time.time()+self.new_session_timeout}
            if time.time() > self.session_info['global']['timeout']:
                self.exit = True
                self.stop_server()
                
        for (idx,session) in enumerate(self.sessions):
            if not session.id in self.session_info:
                self.session_info[session.id] = {'new' : True, 'session': session, 'connection_count':session.connection_count, 'timeout':time.time()+self.new_session_timeout}
            else:
                self.session_info[session.id]['new'] = False
                self.session_info[session.id]['connection_count'] = session.connection_count
                
            print('SESSION_IDX:{0}:CONNECTIONS:{1}'.format(idx, self.session_info[session.id]['connection_count']))
            
            if self.session_info[session.id]['connection_count'] == 0:
                if time.time() > self.session_info[session.id]['timeout']:
                    self.exit = True
                    self.stop_server()
                
            else:
                self.session_info[session.id]['timeout'] = time.time()+self.session_timeout
                
                
    def run_server(self):
        self.bok_io_loop.start()
        
    def stop_server(self):
        self.bok_io_loop.stop()
        print('stopping server on {0}'.format(serv.port))
        
    def get_memory(self):
        process = psutil.Process(os.getpid())
        self.memory_usage = int(process.get_memory_info().rss)
        print('MEMORY:{0}'.format(self.memory_usage))
        

def rest_of_tornado(serv):
    print('starting server on {0}'.format(serv.port))
    while not serv.exit:
        serv.get_memory()
        serv.get_sessions()
        time.sleep(1)

if __name__ == "__main__":
    
    from argparse import ArgumentParser
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("port", metavar="<PORT>", nargs="+")
    args = parser.parse_args()

    if len(args.port) == 0:
        print("Usage: server PORT")
        sys.exit(1)

    # initialize the tornado server
    serv = bokeh_server_wrapper(port=int(args.port[0]))
    serv.setup_bokeh_server()
    
    #
    nadostop = threading.Thread(target=rest_of_tornado,args=(serv,))
    nadostop.daemon = True
    nadostop.start()
    serv.run_server()

    