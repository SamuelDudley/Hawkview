celery -A hawkview_web_server.celery worker --loglevel=INFO --concurrency=1 --maxtasksperchild=1
