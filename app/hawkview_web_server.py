#!/usr/bin/env python
'''
Flask server for Hawkview Web App
Samuel Dudley
Oct 2016
'''
from bokeh.embed import autoload_server # bokeh in the flask app

import eventlet
eventlet.monkey_patch()

from flask_socketio import SocketIO, emit
from flask import Flask, request, render_template, session, redirect, url_for, flash, send_from_directory, jsonify

import sys
from collections import OrderedDict
import time
import arrow
import redis
import simplejson
from celery import Celery
import ast

from plot_app.config import __FLASK_SECRET_KEY, __FLASK_PORT, __FLASK_DEBUG, __BOKEH_DOMAIN_NAME, __BOKEH_PORT
                       
import os, sys, json, uuid, hashlib, random, time, shutil, traceback
import sqlite3 as lite

from werkzeug import secure_filename

from lib.upload_file import uploadfile
from lib.MAVHawkview import Hawkview

APP_ROOT = os.path.dirname(os.path.abspath(__file__))
APP_STATIC = os.path.join(APP_ROOT, 'static')
APP_TEMPLATES = os.path.join(APP_ROOT, 'templates')
APP_UPLOADS = os.path.join(APP_ROOT, 'uploads')

app = Flask(__name__, root_path=APP_ROOT, template_folder=APP_TEMPLATES, static_folder=APP_STATIC)
app.secret_key = __FLASK_SECRET_KEY
UPLOAD_FOLDER = os.path.join(APP_ROOT, 'data')
app.config['MAX_CONTENT_LENGTH'] = 300 * 1024 * 1024 # = 300MB
app.debug = __FLASK_DEBUG

# Celery configuration
# redis://:password@hostname:port/db_number
app.config['CELERY_BROKER_URL'] = 'redis://localhost:6379/0'
app.config['CELERY_RESULT_BACKEND'] = 'redis://localhost:6379/0'
app.config['CELERY_TRACK_STARTED'] = True
app.config['CELERY_SEND_EVENTS'] = True

socketio = SocketIO(app, async_mode='eventlet', message_queue=app.config['CELERY_BROKER_URL'] )

# Initialize Celery
celery = Celery(app.name, broker=app.config['CELERY_BROKER_URL'])
celery.conf.update(app.config)

r = redis.StrictRedis.from_url('redis://localhost:6379/1')

ALLOWED_EXTENSIONS = set(['bin', 'tlog'])
IGNORED_FILES = [ f for f in os.listdir(UPLOAD_FOLDER) if os.path.isfile(os.path.join(UPLOAD_FOLDER,f))]
IGNORED_FILES.append('.gitignore')
print 'IGNORED_FILES', IGNORED_FILES


def get_db_filename():
    return os.path.join(os.getcwd(), 'data', 'logdatabase.db')

@celery.task(bind=True)
def process_log(self, url, log_path, filename, output_path='/tmp/log'):
    """Background task that processes a log with websocket progress reports"""
    
    def progress_bar(pct, end_val=100, bar_length=100):
        percent = float(pct) / end_val
        hashes = '|' * int(round(percent * bar_length))
        spaces = '-' * (bar_length - len(hashes))
         
        print ("\r[ {0} ] {1}%".format(hashes + spaces, int(round(percent * 100))))
        
        meta = {'current': pct, 'total': 100, 'status': 'Processing log', 'log':filename}
        self.update_state(state='PROGRESS', meta=meta)
        local_socketio.emit('log processing', {'data': {'PROGRESS':meta}}, namespace='/celery')
     
    local_socketio = SocketIO(message_queue=url) # setup a websocket to run from the celery task
    
    meta = {'current': 0, 'total': 100, 'status': 'Log processing started', 'log':filename}
    self.update_state(state='STARTING', meta=meta)
    local_socketio.emit('log processing', {'data': {'STARTING':meta}}, namespace='/celery')
     
    # update the task status in the log database
    task = ('PROCESSING',filename)
    con = lite.connect(get_db_filename())
    with con:
        cur = con.cursor()
        sql = ''' UPDATE Logs
              SET Status = ?
              WHERE Id = ?'''
        cur = con.cursor()
        cur.execute(sql, task)
     
    try: 
        name, extension = os.path.splitext(filename)
        hawk = Hawkview(log_path, raw_np_save_path= os.path.join(UPLOAD_FOLDER, name))
        log_result = hawk.process(progress_func = progress_bar)
         
        hawk.cmd_save(args=[])
        meta={'current': 100, 'total': 100,
                                        'status': 'Log processing complete', 'log': filename}
        
        local_socketio.emit('log processing', {'data': {'COMPLETE':meta}}, namespace='/celery')
         
        self.update_state(state='COMPLETE', meta=meta)
        
        task = ('COMPLETE',filename)
        con = lite.connect(get_db_filename())
        with con:
            cur = con.cursor()
            sql = ''' UPDATE Logs
                  SET Status = ?
                  WHERE Id = ?'''
            cur = con.cursor()
            cur.execute(sql, task)
         
        hawk = None
        
    except Exception as e:
        stack_str = traceback.print_exc(e)
        error_str = 'ERROR: An error occurred while processing {0} [ {1} ] [ {2} ]'.format(filename, e, stack_str)
        print error_str
        
        task = ('ERROR', error_str, filename)
        con = lite.connect(get_db_filename())
        with con:
            cur = con.cursor()
            sql = ''' UPDATE Logs
                  SET Status = ?,
                      Error = ?
                  WHERE Id = ?'''
            cur = con.cursor()
            cur.execute(sql, task)
        
        meta={'error':error_str, 'status': 'Log processing error', 'log': filename}
        local_socketio.emit('log processing', {'data': {'ERROR':meta}}, namespace='/celery')
        self.update_state(state='ERROR',meta=meta)
    
    # TODO: email user when log is ready
    
    return {'log':filename}

def allowed_file(filename):
    return '.' in filename and \
        filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def gen_file_name(filename):
    """ create a new file name for the log """
    name, extension = os.path.splitext(filename)
    name = str(uuid.uuid4())
    filename = '%s%s' % (name, extension.lower())
    
    # if the file name exist already, rename it and return a new name
    while os.path.exists(os.path.join(UPLOAD_FOLDER, filename)):
        name, extension = os.path.splitext(filename)
        filename = '%s%s' % (str(uuid.uuid4()), extension.lower())
        
    return filename


def md5sum(filename, blocksize=65536):
    file_path = os.path.join(UPLOAD_FOLDER, filename)
    hash = hashlib.md5()
    with open(file_path, "rb") as f:
        for block in iter(lambda: f.read(blocksize), b""):
            hash.update(block)
    return hash.hexdigest()


@app.route("/upload", methods=['GET', 'POST'])
def upload():
    if request.method == 'POST':
        print request.form
        email = request.form['email']
        discription = request.form['textarea']
        # TODO: email user when log is ready
        file = request.files['file']
        result = None
        if file:
            filename = secure_filename(file.filename)
            original_filename = filename 
            filename = gen_file_name(filename)
            mimetype = file.content_type


            if not allowed_file(file.filename):
                result = uploadfile(name=filename, type=mimetype, size=0, not_allowed_msg="Filetype not allowed")

            else:
                uploaded_file_path = os.path.join(UPLOAD_FOLDER, filename)
                # save the file to the server
                file.save(uploaded_file_path)

                # get file size after saving
                size = os.path.getsize(uploaded_file_path)

                # get the md5 hash for the file
                hash = md5sum(filename)
                
                # check the database to see if the file has already been uploaded                
                con = lite.connect(get_db_filename())
                with con:
                    cur = con.cursor()
                    sql = "SELECT * FROM Logs WHERE Hash=?"
                    cur.execute(sql, [(hash)])
                    res = cur.fetchone()
                    if res is not None:
                        if len(res) >= 1:
                            # a file with the same hash already exists...
                            # return a link to the existing file for js upload call back
                            result = uploadfile(name=res[0], type=mimetype, size=res[12])
                            delete(filename)
                    
                    else:
                        # create a row in the log database for the newly uploaded log                    
                        rows = [(filename, '', discription, time.strftime('%Y-%m-%d %H:%M:%S'), 0, 0, 'Hawkview.io', email, '', 1, str(uuid.uuid4()),
                                 hash, size, 'UPLOADED', '')]
                        cur.executemany('INSERT INTO Logs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', rows)
                        con.commit()
                
                if result is None:
                    # create json for js upload call back
                    result = uploadfile(name=filename, type=mimetype, size=size, original_name=original_filename)
                    
                    # start the background celery task...
                    task = process_log.apply_async((app.config['CELERY_BROKER_URL'],os.path.join(APP_ROOT,result.get_file()['url']),filename))
                    print(task.id)
            
            # return json for js upload call back   
            return simplejson.dumps({"files": [result.get_file()]})

    if request.method == 'GET':
        # get all file in ./data directory
        files = [ f for f in os.listdir(UPLOAD_FOLDER) if os.path.isfile(os.path.join(UPLOAD_FOLDER,f)) and f not in IGNORED_FILES ]
        for file in files:
            IGNORED_FILES.append(file)
        file_display = []

        for f in files:
            size = os.path.getsize(os.path.join(UPLOAD_FOLDER, f))
            file_saved = uploadfile(name=f, size=size)
            file_display.append(file_saved.get_file())

        return simplejson.dumps({"files": file_display})

    return redirect(url_for('index'))


# TODO: only delete the database entry and think about how to deal with who can remove files
# @app.route("/delete/<string:filename>", methods=['DELETE'])
def delete(filename):
    file_path = os.path.join(UPLOAD_FOLDER, filename)
    name, extension = os.path.splitext(filename)
    file_path_analysis = os.path.join(UPLOAD_FOLDER, name)
 
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
                 
            if os.path.isdir(file_path_analysis):
                shutil.rmtree(file_path_analysis)
             
            return simplejson.dumps({filename: 'True'})
        except:
            return simplejson.dumps({filename: 'False'})


# Allow the download of files from the server
@app.route("/data/<string:filename>", methods=['GET'])
def get_file(filename):
    return send_from_directory(os.path.join(UPLOAD_FOLDER), filename=filename)

@app.route('/', methods=['GET', 'POST'])
def index():
    return render_template('index.html')

def read_json(file_path):
    with open(file_path, 'r') as fid:
        json_data = json.load(fid)
    return json_data

@app.route('/analysis/<log_id>', methods=['GET', 'POST'])
def analysis(log_id):
    # check the log database andmake sure we it is ready for analysis
    con = lite.connect(get_db_filename())
    with con:
        cur = con.cursor()
        sql = "SELECT Status FROM Logs WHERE Id=?"
        cur.execute(sql, [(log_id)])
        res = cur.fetchone()
        log_status = res[0]
        
    if log_status == 'ERROR':
        flash('This log encountered error(s) during processing and is not available for analysis...')
        # TODO: add link to allow notification of web-admin
        return redirect(url_for('browse'))
    elif (log_status == 'PROCESSING' or log_status == 'STARTING'):
        flash('This log is still currently processing and is not currently available for analysis...')
        return redirect(url_for('browse'))
    elif log_status == 'UPLOADED':
        flash('This log is queued for processing and is not currently available for analysis...')
        return redirect(url_for('browse'))
    else:
        # log status is 'COMPLETE' allow analysis
        pass
    
        
    
    return_channel = 'plot_manager-'+str(uuid.uuid4())
    r.publish('web_server', {'plot_request':return_channel})
    
    # generate graphs and run the analysis for this log id
    print('Starting analysis for log id: {0}'.format(log_id))
    
    [log_name,log_extension] = log_id.split('.')
    print log_name,log_extension
    log_folder = os.path.join(UPLOAD_FOLDER,log_name)
    
    try:
        graphs_json = os.path.join(log_folder, 'graphs.json')
        graphs = read_json(graphs_json)
    except:
        graphs = []
        
    try:
        params_json = os.path.join(log_folder, 'params.json')
        params = read_json(params_json)
    except:
        params = []
    
    try:
        flightmodes_json  = os.path.join(log_folder, 'flightmodes.json')
        flightmodes = read_json(flightmodes_json)
    except:
        flightmodes = []
    
    try:
        messages_json = os.path.join(log_folder, 'messages.json')
        messages = read_json(messages_json)
    except:
        messages = []
    
    for graph in graphs:
        print graph['path']
#         print graph['expression']
#         print graph['description']
#         print graph['name']

    s = r.pubsub(ignore_subscribe_messages=True)
    s.subscribe(return_channel)
    
    data = {}
    bokeh_port = -1
    
    end_wait = time.time()+3 # seconds
    while time.time() < end_wait:
        
        plot_manager_data = s.get_message()
        if plot_manager_data is not None:
            try:
                data = ast.literal_eval(plot_manager_data['data'])
                print data
            except Exception as e:
                print('ERROR: {0}'.format(e))
            
            if 'port' in data.keys():
                bokeh_port = data['port']
                print "got port", bokeh_port
                break
            
        time.sleep(0.01)
    s.unsubscribe()
        
    
    if bokeh_port == 0:
        flash('No bokeh servers currently available... Please try again shortly')
        return redirect(url_for('browse'))
    
    if bokeh_port == -1:
        flash('There was an error communicating with the bokeh servers... Please try again later')
        return redirect(url_for('browse'))
    
    bokeh_server_url = 'http://' + __BOKEH_DOMAIN_NAME +':'+str(bokeh_port)+'/'
    bokeh_session_id = str(uuid.uuid4())
    script = autoload_server(model=None,
                         app_path="/plot_app",
                         session_id= log_name+":"+bokeh_session_id, # we pass the log id in front of a
                         # unique session id. There might be a better way to do this with bokeh but
                         # this works for now...
                         url=bokeh_server_url)
    
    return render_template('analysis.html', plot_script = script, log_id = log_id, graphs = graphs, 
                           params = params, flightmodes = flightmodes, messages = messages)


@app.route('/browse', methods=['GET', 'POST'])
def browse():
    headderNames = ["ID", "Uploaded", "Status", "Size"]
    con = lite.connect(get_db_filename())
    with con:
        cur = con.cursor()
        sql = "SELECT Id,Date,Status,LogSize FROM Logs"
        cur.execute(sql)
        logs = cur.fetchall()
    
#   logs is a list of tuples... To change values we do a list conversion
    for (idx,log) in enumerate(logs):
        log = list(logs[idx])
        log[1] = arrow.get(log[1]).humanize()
        logs[idx] = log
        
    return render_template('logs.html', headderNames = headderNames, logs = logs)


@app.route('/about', methods=['GET', 'POST'])
def about():
    return render_template('about.html')


@socketio.on('connect', namespace='/celery')
def celery_connect():
    print('Client connected to celery ws')
    

@socketio.on('disconnect', namespace='/celery')
def celery_disconnect():
    print('Client disconnected from celery ws')


def start_server():
    socketio.run(app, host='0.0.0.0',port=__FLASK_PORT, debug=__FLASK_DEBUG)

    
if __name__ == '__main__':
    start_server()

    
