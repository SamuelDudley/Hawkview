'''
Cesium map module
Samuel Dudley
Jan 2016
'''
import os, json, time, sys, uuid, urllib2


from autobahn.twisted.websocket import WebSocketServerProtocol, WebSocketServerFactory
from autobahn.twisted.resource import WebSocketResource, WSGIRootResource
from twisted.web.server import Site
from twisted.web.wsgi import WSGIResource
from twisted.internet import reactor

from twisted.python import log

import hawkview_web_server # the Flask webapp
APP_DEBUG = True
import Queue, threading


class ServerProtocol(WebSocketServerProtocol):

    def onConnect(self, request):
        if APP_DEBUG:
            print("Client connecting: {0}".format(request.peer))

    def onOpen(self):
        if APP_DEBUG:
            print("WebSocket connection open")
        self.id = uuid.uuid4()
        self.factory.data[self.id]=self
        payload = {'new_connection':self.id}
        self.factory.message_queue.put(payload)

    def onMessage(self, payload, isBinary):
        if isBinary:
            # TODO: handle binary
            pass
        else:
            # It's text based (JSON)
            payload = json.loads(payload)
            self.factory.message_queue.put(payload)

    def onClose(self, wasClean, code, reason):
        if APP_DEBUG:
            print("WebSocket connection closed: {0}".format(reason))
        try:
            del self.factory.data[self.id]
        except Exception as e:
            print("An error occurred when attempting to close a websocket: {}".format(e))

        
class Server():

    def __init__(self):      
        self.server_thread = None
        self.run_server()
            
    def run_server(self):
#         log.startLogging(sys.stdout)
        
        # create a Twisted Web resource for our WebSocket server
        self.factory = WebSocketServerFactory(u"ws://0.0.0.0:5000")
        self.factory.protocol = ServerProtocol
        self.factory.setProtocolOptions(maxConnections=100)
        self.factory.data = {}
        self.factory.message_queue = Queue.Queue()
        wsResource = WebSocketResource(self.factory)
        
        # create a Twisted Web WSGI resource for our Flask server
        wsgiResource = WSGIResource(reactor, reactor.getThreadPool(), hawkview_web_server.app)
        
        # create a root resource serving everything via WSGI/Flask, but
        # the path "/ws" served by our WebSocket stuff
        rootResource = WSGIRootResource(wsgiResource, {b'ws': wsResource})
    
        # create a Twisted Web Site and run everything
        
        site = Site(rootResource)
        reactor.listenTCP(5002, site, interface="0.0.0.0")
        self.server_thread = threading.Thread(target=reactor.run, args=(False,))
        self.server_thread.daemon = True
        self.server_thread.start()
        self.server_thread.join()
        
    def stop_server(self):
        if self.server_thread is not None:
            reactor.callFromThread(reactor.stop) # Kill the server talking to the browser
            while self.server_thread.isAlive():
                time.sleep(0.01) #TODO: handle this better...
            
    def send_data(self, data, target = None):
        '''push json data to the browser'''
        payload = json.dumps(data).encode('utf8')
        if target is not None:
            connection = self.factory.data[target]
            reactor.callFromThread(WebSocketServerProtocol.sendMessage, connection,  payload)
        else:   
            for connection in self.factory.data.values():
                reactor.callFromThread(WebSocketServerProtocol.sendMessage, connection,  payload)
    
serv = Server()
