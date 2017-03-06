pkill screen

cd redis-3.2.4/src
# start the redis server
screen -S redis_server -dm bash -c './redis-server'

cd ../..

# start the bokeh server pool manager
screen -S bokeh_server -dm bash -c 'python bokeh_manager.py'

# start the flask webserver
screen -S web_server -dm bash -c 'python hawkview_web_server.py'

# start the celery server
screen -S celery_server -dm bash -c 'celery worker -A hawkview_web_server.celery -P eventlet --loglevel=INFO --concurrency=1 --maxtasksperchild=1'

