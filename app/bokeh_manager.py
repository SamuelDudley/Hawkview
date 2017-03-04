import tornado
import tornado.ioloop
import tornado.options
import tornado.autoreload
import sys

import os
import psutil
import subprocess        

if __name__ == "__main__":
    #initialize the tornado servers
    ports = [5008,5009]
    for port in ports:
        subprocess.Popen(Server(port=port))
    
    
    
    
    