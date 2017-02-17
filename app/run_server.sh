pkill screen

cd redis-3.2.4/src
# start the redis server
screen -S redis_server -dm bash -c './redis-server'

cd ../..

# start the bokeh server
screen -S bokeh_server -dm bash -c 'bokeh serve --allow-websocket-origin=127.0.0.1:5002 plot_app'

# start the flask webserver
screen -S web_server -dm bash -c 'python hawkview_web_server.py'

# start the celery server
screen -S celery_server -dm bash -c 'celery -A hawkview_web_server.celery worker --loglevel=INFO --concurrency=1 --maxtasksperchild=1'

#cd lib
#screen -S bokeh_server -dm bash -c 'bokeh serve --allow-websocket-origin=127.0.0.1:5002 ardupilot_plot.py'

