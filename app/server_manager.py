from subprocess import PIPE, Popen
import signal, time
import redis
import ast



class server_manager():
    def __init__(self):
        self.r = redis.StrictRedis.from_url('redis://localhost:6379/1')
        self.s = self.r.pubsub(ignore_subscribe_messages=True)
        self.s.subscribe('web_server')
        self.p = {}
        self.ports = [5009,5008]
        self.start_time = time.time()
        self.free_ports = self.ports
        self.procs_to_remove = []
        self.exit = False
    
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)
        
        self.watch_servers()
        self.check_free_ports()
        
        self.main()
        
    
    def main(self):
        print("Started the bokeh server manager: {}".format(self.free_ports))
        while not self.exit:
            self.watch_servers()
            self.check_free_ports()
            web_server_data = self.s.get_message()
            data = {}
            if web_server_data is not None:
                try:
                    data = ast.literal_eval(web_server_data['data'])
                except Exception as e:
                    print('ERROR: {0}'.format(e))
                
                if 'plot_request' in data.keys():
                    if len(self.free_ports) > 0:
                        self.launch_servers([self.free_ports[0]])
                        time.sleep(3)
                        self.r.publish('plot_manager', {'port':self.free_ports[0]})
                    else:
                        print('NO FREE BOKEH SERVERS!')
                        self.r.publish('plot_manager', {'port':0})
            
            time.sleep(0.01)
    
    def exit_gracefully(self, signum, frame):
        self.exit = True
        self.shutdown_all_servers()
        while len(self.p) > 0:
            self.watch_servers()
        
        
    def check_free_ports(self):
        self.free_ports = [x for x in self.ports if str(x) not in self.p.keys()]
        
    def launch_servers(self, ports):
        for port in ports:
            self.p[str(port)] = Popen(["python", "-u", "server_wrapper.py", str(port)], stdout=PIPE, bufsize=1)
    
    def clear_servers(self):
        for proc in self.procs_to_remove:
                self.p.pop(proc, None)
        self.procs_to_remove = []
    
    def watch_servers(self):
        self.clear_servers()     
        for proc in self.p:
            if self.p[proc].poll() is None:
                output =  self.p[proc].stdout.readline() # read output
                print proc, output
                # TODO use the info to work out which servers can have sessions added
            else:
                self.procs_to_remove.append(proc)
                
    def shutdown_all_servers(self):
        for proc in self.p:
            self.shutdown_server(proc)
                
    def shutdown_server(self, proc):
        if self.p[proc].poll() is None:
            self.p[proc].terminate()
                

if __name__ == "__main__":
    serv_man = server_manager()
        