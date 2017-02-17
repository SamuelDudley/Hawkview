#!/usr/bin/env python
'''
Flask server for Hawkview Web App
Samuel Dudley
Oct 2016
'''
from plot_app.config import __FLASK_SECRET_KEY, __FLASK_PORT, __FLASK_DEBUG, __BOKEH_DOMAIN_NAME, __BOKEH_PORT                           
import os, sys, json, uuid, hashlib, random, time, shutil, traceback
import sqlite3 as lite

import bokeh
from bokeh.io import curdoc

import simplejson
from celery import Celery

from flask import Flask, request, render_template, session, redirect, url_for, flash, send_from_directory, jsonify
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

# Celery configuration
app.config['CELERY_BROKER_URL'] = 'redis://localhost:6379/0'
app.config['CELERY_RESULT_BACKEND'] = 'redis://localhost:6379/0'

# Initialize Celery
celery = Celery(app.name, broker=app.config['CELERY_BROKER_URL'])
celery.conf.update(app.config)


ALLOWED_EXTENSIONS = set(['bin', 'tlog'])
IGNORED_FILES = [ f for f in os.listdir(UPLOAD_FOLDER) if os.path.isfile(os.path.join(UPLOAD_FOLDER,f))]
IGNORED_FILES.append('.gitignore')
print 'IGNORED_FILES', IGNORED_FILES


def get_db_filename():
    return os.path.join(os.getcwd(), 'data', 'logdatabase.db')


@celery.task(bind=True)
def process_log(self, log_path, filename, output_path='/tmp/log') :
    """Background task that runs a long function with progress reports."""
    
    def progress_bar(pct, end_val=100, bar_length=100):
        percent = float(pct) / end_val
        hashes = '|' * int(round(percent * bar_length))
        spaces = '-' * (bar_length - len(hashes))
        
        print ("\r[ {0} ] {1}%".format(hashes + spaces, int(round(percent * 100))))
        
        self.update_state(state='PROGRESS',
                              meta={'current': pct, 'total': 100,
                                    'status': 'Processing'})
    
    name, extension = os.path.splitext(filename)
    hawk = Hawkview(log_path, raw_np_save_path= os.path.join(UPLOAD_FOLDER, name))
    log_result = hawk.process(progress_func = progress_bar)
    
    hawk.cmd_save(args=[])
    
    self.update_state(state='COMPLETE',
                              meta={'current': 100, 'total': 100,
                                    'status': 'Task completed!', 'result': 42})
    hawk = None
    return {}

def allowed_file(filename):
    return '.' in filename and \
        filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def gen_file_name(filename):
    """
    If file name exist already, rename it and return a new name
    """
    name, extension = os.path.splitext(filename)
    name = str(uuid.uuid4())
    filename = '%s%s' % (name, extension)
    
    i = 1
    while os.path.exists(os.path.join(UPLOAD_FOLDER, filename)):
        name, extension = os.path.splitext(filename)
        filename = '%s_%s%s' % (name, str(i), extension)
        i = i + 1

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
                print size
                # get the md5 hash for the file
                hash = md5sum(filename)
                
                # check the database to see if the file has already been uploaded
                print('HASH', hash)
                
                # create a row in the log database for the newly uploaded log
                
                con = lite.connect(get_db_filename())
                with con:
                    cur = con.cursor()
                    sql = "SELECT * FROM Logs WHERE Hash=?"
                    cur.execute(sql, [(hash)])
                    res = cur.fetchone()
                    if res is not None:
                        if len(res) >= 1:
                            # a file with the same hash already exists...
                            # return a link to the existing file
                            result = uploadfile(name=res[0], type=mimetype, size=res[12])
                            delete(filename)
                    
                    else:                    
                        rows = [(filename, '', discription, time.strftime('%Y-%m-%d %H:%M:%S'), 0, 0, 'Hawkview.io', email, '', 1, str(uuid.uuid4()),
                                 hash, size, 'UPLOADED')]
                        cur.executemany('INSERT INTO Logs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)', rows)
                        con.commit()
                
                if result is None:
                    # return json for js call back
                    result = uploadfile(name=filename, type=mimetype, size=size)
                    task = process_log.apply_async((os.path.join(APP_ROOT,result.get_file()['url']),filename))
                    print task.id
                
#                 task = long_task.apply_async()
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


@app.route('/status/<task_id>')
def taskstatus(task_id):
    task = process_log.AsyncResult(task_id)
    if task.state == 'PENDING':
        # job has not started yet
        response = {
            'state': task.state,
            'current': 0,
            'total': 1,
            'status': 'Pending...'
        }
    elif task.state != 'FAILURE':
        response = {
            'state': task.state,
            'current': task.info.get('current', 0),
            'total': task.info.get('total', 1),
            'status': task.info.get('status', '')
        }
        if 'result' in task.info:
            response['result'] = task.info['result']
    else:
        # something went wrong in the background job
        response = {
            'state': task.state,
            'current': 1,
            'total': 1,
            'status': str(task.info),  # this is the exception raised
        }
    return jsonify(response)


# Allow the download of files from the server
@app.route("/data/<string:filename>", methods=['GET'])
def get_file(filename):
    return send_from_directory(os.path.join(UPLOAD_FOLDER), filename=filename)

@app.route('/', methods=['GET', 'POST'])
def index():
    return render_template('index.html')

@app.route('/analysis/<log_id>', methods=['GET', 'POST'])
def analysis(log_id):
    from bokeh.embed import autoload_server
    # generate graphs and run the analysis for this log id
    print ('Starting analysis for log id:', log_id)
    
    [log_name,log_extension] = log_id.split('.')
    print log_name,log_extension
    log_folder = os.path.join(UPLOAD_FOLDER,log_name)
    graphs_json = os.path.join(log_folder, 'graphs.json')
    params_json = os.path.join(log_folder, 'params.json')
    flightmodes_json  = os.path.join(log_folder, 'flightmodes.json')
    messages_json = os.path.join(log_folder, 'messages.json')
    
    with open(graphs_json, 'r') as fid:
        graphs = json.load(fid)
#     params = json.load(params_json)
#     flightmodes = json.load(flightmodes_json)
#     messages = json.load(messages_json)
    
    for graph in graphs:
        print graph['path']
#         print graph['expression']
#         print graph['description']
#         print graph['name']
    bokeh_server_url = 'http://' + __BOKEH_DOMAIN_NAME +':'+__BOKEH_PORT+'/'
    bokeh_session_id = str(uuid.uuid4())
    script = autoload_server(model=None,
                         app_path="/plot_app",
                         session_id= log_name+":"+bokeh_session_id, # we pass the log id in front of a
                         # unique session id. There might be a better way to do this with bokeh but
                         # this works for now...
                         url=bokeh_server_url)
    
    return render_template('analysis.html', plot_script = script, log_id = log_id, graphs = graphs)

@app.route('/browse', methods=['GET', 'POST'])
def browse():
    headderNames = ["ID", "Date", "Status", "LogSize"]
    con = lite.connect(get_db_filename())
    with con:
        cur = con.cursor()
        sql = "SELECT Id,Date,Status,LogSize FROM Logs"
        cur.execute(sql)
        res = cur.fetchall()
    
    print res
    return render_template('logs.html', headderNames=headderNames, logs=res)

@app.route('/about', methods=['GET', 'POST'])
def about():
    return render_template('about.html')

def start_server():

    if not __FLASK_DEBUG:
        import logging
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)
    
    app.run(host='0.0.0.0',port=__FLASK_PORT, threaded=True, debug=__FLASK_DEBUG)
    
if __name__ == '__main__':
    start_server()
    
    
