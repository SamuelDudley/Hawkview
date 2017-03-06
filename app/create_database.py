# Script to create or upgrade the SQLite DB

import sqlite3 as lite
import sys
import os

# this is needed for the following imports
# sys.path.append(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'plot_app'))
# from plot_app.config import get_db_filename, get_log_filepath, \
#     get_cache_filepath, get_kml_filepath

def get_log_filepath():
    return os.path.join(os.getcwd(), 'data')

def get_db_filename():
    return os.path.join(os.getcwd(), 'data', 'logdatabase.db')


log_dir = get_log_filepath()
if not os.path.exists(log_dir):
    print('creating log directory '+log_dir)
    os.makedirs(log_dir)


print('creating DB at '+get_db_filename())
con = lite.connect(get_db_filename())
with con:
    cur = con.cursor()

    # Logs table (contains information not found in the log file)
    cur.execute("PRAGMA table_info('Logs')")
    columns = cur.fetchall()

    if len(columns) == 0:
        cur.execute("CREATE TABLE Logs("
                "Id TEXT, " # log id (part of the file name)
                "Title TEXT, "
                "Description TEXT, "
                "Date TIMESTAMP, " # date & time when uploaded
                "AllowForAnalysis INTEGER, " # if 1 allow for statistical analysis
                "Obfuscated INTEGER, "
                "Source TEXT, " # where it comes from: 'webui', 'CI', 'QGroundControl'
                "Email TEXT, " # email (may be empty)
                "Type TEXT, " # upload type: 'personal' (or '') or 'flightreport'
                "Public INT, " # if 1 this log can be publicly listed
                "Token TEXT, " # Security token (currently used to delete the entry)
                "Hash TEXT, " # md5 hash for this log
                "LogSize INT, " # size of the log on disk
                "Status TEXT, " # status of log processing
                "Error TEXT, " # error trace when processing the log (if any)
                "CONSTRAINT Id_PK PRIMARY KEY (Id))")


    # LogsGenerated table (information from the log file, for faster access)
    cur.execute("PRAGMA table_info('LogsGenerated')")
    columns = cur.fetchall()

    if len(columns) == 0:
        cur.execute("CREATE TABLE LogsGenerated("
                "Id TEXT, " # log id
                "Duration INT, " # logging duration in [s]
                "MavType TEXT, " # vehicle type
                "Estimator TEXT, "
                "AutostartId INT, " # airframe config
                "Hardware TEXT, " # board
                "Software TEXT, " # software (git tag)
                "NumLoggedErrors INT, " # number of logged error messages (or more severe)
                "NumLoggedWarnings INT, "
                "FlightModes TEXT, " # all flight modes as comma-separated int's
                "SoftwareVersion TEXT, " # release version
                "CONSTRAINT Id_PK PRIMARY KEY (Id))")
con.close()