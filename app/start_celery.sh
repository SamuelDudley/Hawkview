celery worker -A hawkview_web_server.celery -P eventlet --loglevel=DEBUG --concurrency=1 --maxtasksperchild=1
