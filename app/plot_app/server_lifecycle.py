import os
def on_server_loaded(server_context):
    ''' If present, this function is called when the server first starts. '''
    print("SERVER:LOADED:{0}".format(os.getpid()))

def on_server_unloaded(server_context):
    ''' If present, this function is called when the server shuts down. '''
    print("SERVER:UNLOADED:{0}".format(os.getpid()))

def on_session_created(session_context):
    ''' If present, this function is called when a session is created. '''
    print("SESSION:CREATED:{0}".format(os.getpid()))

def on_session_destroyed(session_context):
    ''' If present, this function is called when a session is closed. '''
    print("SESSION:DESTROYED:{0}".format(os.getpid()))
